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
        completed = ws.receive_json()
        assert completed['type'] == 'complete'
        assert completed['frames'] == 3
        assert completed['report']['statistics']['frames'] == 3
        assert completed['report']['outcome'] == 'completed'
        assert ws.receive()['type'] == 'websocket.close'
    assert all(not p.exists() for p in paths)
    assert engines[0].closed


def test_upload_limit(rig):
    client, engines = rig
    with client.websocket_connect('/ws/analyze') as ws:
        ws.send_json({'exercise':'pushup', 'mode':'upload', 'size':server.MAX_FILE+1})
        assert ws.receive_json()['type'] == 'error'
    assert not engines


def test_invalid_json_shape(rig):
    client, engines = rig
    with client.websocket_connect('/ws/analyze') as ws:
        ws.send_json([])
        assert ws.receive_json()['message'] == 'Session configuration must be an object'
    assert not engines


def test_cross_origin_rejected(rig):
    client, engines = rig
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect('/ws/analyze', headers={'origin':'https://other.example'}):
            pass
    assert exc.value.code == 1008
    assert not engines


def test_text_camera_frame_rejected(rig):
    client, engines = rig
    with client.websocket_connect('/ws/analyze') as ws:
        ready(ws)
        ws.send_text('not binary')
        assert ws.receive_json()['message'] == 'Expected binary video data'
    assert engines[0].closed


def test_engine_failure_message(rig, monkeypatch):
    client, _ = rig
    def broken(exercise):
        raise SyntaxError('expected argument value expression', ('pose_exercise_analyzer.py',229,1,'log='))
    monkeypatch.setattr(server, 'create_engine', broken)
    with client.websocket_connect('/ws/analyze') as ws:
        ws.send_json({'exercise':'pushup', 'mode':'live'})
        assert ws.receive_json()['type'] == 'status'
        assert ws.receive_json()['type'] == 'status'
        assert 'line 229' in ws.receive_json()['message']


def test_disconnect_during_initialization_closes_engine(rig, monkeypatch):
    import threading
    client, engines = rig
    original = server.create_engine
    entered, release = threading.Event(), threading.Event()
    def slow(exercise):
        entered.set()
        assert release.wait(5)
        return original(exercise)
    monkeypatch.setattr(server, 'create_engine', slow)
    timer = threading.Timer(.1, release.set)
    try:
        with client.websocket_connect('/ws/analyze') as ws:
            ws.send_json({'exercise':'pushup','mode':'live'})
            ws.receive_json()
            ws.receive_json()
            assert entered.wait(5)
            timer.start()
        assert len(engines) == 1
        assert engines[0].closed
    finally:
        release.set()
        timer.cancel()


def test_live_stop_returns_report(rig):
    client, engines = rig
    with client.websocket_connect('/ws/analyze') as ws:
        ready(ws)
        ws.send_bytes(jpeg())
        assert ws.receive_json()['type'] == 'result'
        ws.send_json({'type':'stop'})
        completed = ws.receive_json()
        assert completed['type'] == 'complete'
        assert completed['report']['outcome'] == 'stopped'
        assert completed['report']['statistics']['frames'] == 1
        assert ws.receive()['type'] == 'websocket.close'
    assert engines[0].closed


def test_stop_before_upload_is_finished_cleans_file(rig):
    client, engines = rig
    with client.websocket_connect('/ws/analyze') as ws:
        ready(ws, mode='upload', size=100)
        ws.send_bytes(b'partial')
        ws.send_json({'type':'stop'})
        completed = ws.receive_json()
        assert completed['report']['statistics']['frames'] == 0
        assert completed['report']['outcome'] == 'stopped'
        assert ws.receive()['type'] == 'websocket.close'
    assert engines[0].closed


def test_interrupted_session_retains_partial_report(rig):
    client, _ = rig
    with client.websocket_connect('/ws/analyze') as ws:
        ready(ws)
        ws.send_bytes(jpeg())
        ws.receive_json()
        ws.send_bytes(b'invalid')
        error = ws.receive_json()
        assert error['type'] == 'error'
        assert error['report']['outcome'] == 'interrupted'
        assert error['report']['statistics']['frames'] == 1
