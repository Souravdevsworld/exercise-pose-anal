from dataclasses import dataclass
from types import SimpleNamespace

import cv2
from fastapi.testclient import TestClient
import numpy as np
import pytest
import server

@dataclass
class Result:
    exercise: str
    reps: int
    stage: str = 'up'
    angle: float = 160
    feedback: str = 'Good form'
    person_detected: bool = True
    timestamp: float = 0

@pytest.fixture
def rig(monkeypatch):
    engines = []
    class Engine:
        def __init__(self, exercise):
            self.exercise, self.calls, self.closed = exercise, 0, False
            self.estimator = SimpleNamespace(pose=SimpleNamespace(close=self.close))
            engines.append(self)
        def process_frame(self, frame):
            self.calls += 1
            return frame, Result(self.exercise, self.calls)
        def close(self):
            self.closed = True
    monkeypatch.setattr(server, 'create_engine', Engine)
    with TestClient(server.app) as client:
        yield client, engines


def ready(ws, **extra):
    ws.send_json({'exercise': 'pushup', 'mode': 'live', **extra})
    assert ws.receive_json()['type'] == 'status'
    assert ws.receive_json()['type'] == 'status'
    assert ws.receive_json()['type'] == 'ready'


def jpeg():
    return cv2.imencode('.jpg', np.zeros((48, 64, 3), np.uint8))[1].tobytes()


def test_page(rig):
    client, _ = rig
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200


def test_live_sessions_are_isolated(rig):
    client, engines = rig
    with client.websocket_connect('/ws/analyze') as a:
        ready(a)
        with client.websocket_connect('/ws/analyze') as b:
            ready(b, exercise='situp')
            a.send_bytes(jpeg())
            assert a.receive_json()['analysis']['reps'] == 1
            a.send_bytes(jpeg())
            assert a.receive_json()['analysis']['reps'] == 2
            b.send_bytes(jpeg())
            result = b.receive_json()
            assert result['analysis']['reps'] == 1
            assert result['analysis']['exercise'] == 'situp'
    assert len(engines) == 2
    assert all(e.closed for e in engines)


def test_invalid_config(rig):
    client, engines = rig
    with client.websocket_connect('/ws/analyze') as ws:
        ws.send_json({'exercise': 'invalid', 'mode': 'live'})
        assert ws.receive_json()['type'] == 'error'
    assert not engines


def test_invalid_frame(rig):
    client, engines = rig
    with client.websocket_connect('/ws/analyze') as ws:
        ready(ws)
        ws.send_bytes(b'invalid')
        assert ws.receive_json()['type'] == 'error'
    assert engines[0].closed


def test_upload_every_frame_and_delete(rig, tmp_path, monkeypatch):
    client, engines = rig
    path = tmp_path / 'input.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (64, 48))
    for _ in range(3):
        writer.write(np.zeros((48,64,3), np.uint8))
    writer.release()
    data = path.read_bytes()
    original = server.tempfile.NamedTemporaryFile
    paths = []
    def temp(**kwargs):
        f = original(**kwargs)
        paths.append(server.Path(f.name))
        return f
    monkeypatch.setattr(server.tempfile, 'NamedTemporaryFile', temp)
    with client.websocket_connect('/ws/analyze') as ws:
        ready(ws, mode='upload', size=len(data))
        ws.send_bytes(data)
        for n in range(1,4):
            result = ws.receive_json()
            assert result['analysis']['reps'] == n
            ws.send_text('ack')
        assert ws.receive_json() == {'type': 'complete', 'frames': 3}
        assert ws.receive()['type'] == 'websocket.close'
    assert all(not p.exists() for p in paths)
    assert engines[0].closed


def test_upload_limit(rig):
    client, engines = rig
    with client.websocket_connect('/ws/analyze') as ws:
        ready(ws, mode='upload', size=server.MAX_FILE+1)
        assert ws.receive_json()['type'] == 'error'
    assert engines[0].closed
