"""Web transport for the unmodified exercise engine. One engine per connection."""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import anyio
from pathlib import Path
import tempfile

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
MAX_FILE = 100 * 1024 * 1024
MAX_FRAME = 2 * 1024 * 1024
MAX_SESSIONS = 4
slots = asyncio.Semaphore(MAX_SESSIONS)
app = FastAPI(title="Motionlab")
app.mount('/static', StaticFiles(directory=ROOT / 'web'), name='static')


def create_engine(exercise):
    # Lazy import lets the web server start even before model dependencies are installed.
    from pose_exercise_analyzer import ExerciseEngine
    return ExerciseEngine(exercise)


def analyze(engine, frame):
    if frame is None or frame.size == 0:
        raise ValueError('Unable to decode video frame')
    height, width = frame.shape[:2]
    if max(height, width) > 1280:
        frame = cv2.resize(frame, (round(width * 1280 / max(height, width)),
                                   round(height * 1280 / max(height, width))))
    annotated, result = engine.process_frame(frame)
    ok, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise ValueError('Unable to encode analysis frame')
    return {'type': 'result', 'analysis': asdict(result),
            'image': base64.b64encode(jpeg).decode('ascii')}


@app.get('/')
def index():
    return FileResponse(ROOT / 'web' / 'index.html')


@app.websocket('/ws/analyze')
async def session(ws: WebSocket):
    await ws.accept()
    executor = ThreadPoolExecutor(max_workers=1)
    loop = asyncio.get_running_loop()
    acquired = False
    engine = None
    capture = None
    path = None

    async def run(fn, *args):
        return await loop.run_in_executor(executor, fn, *args)

    try:
        config = await asyncio.wait_for(ws.receive_json(), 30)
        exercise, mode = config.get('exercise'), config.get('mode')
        if exercise not in ('pushup', 'situp') or mode not in ('live', 'upload'):
            raise ValueError('Choose push-ups or sit-ups and a valid input mode')
        await ws.send_json({'type': 'status', 'message': 'Waiting for an analysis slot…'})
        await asyncio.wait_for(slots.acquire(), 30)
        acquired = True
        await ws.send_json({'type': 'status', 'message': 'Loading your private analyzer…'})
        engine = await run(create_engine, exercise)
        await ws.send_json({'type': 'ready'})
        if mode == 'upload':
            size = config.get('size')
            if type(size) is not int or not 0 < size <= MAX_FILE:
                raise ValueError('Select a video smaller than 100 MB')
            with tempfile.NamedTemporaryFile(suffix='.video', delete=False) as target:
                path = Path(target.name)
                received = 0
                while received < size:
                    chunk = await asyncio.wait_for(ws.receive_bytes(), 60)
                    received += len(chunk)
                    if not chunk or len(chunk) > MAX_FRAME or received > size:
                        raise ValueError('Invalid video upload')
                    target.write(chunk)
            capture = await run(cv2.VideoCapture, str(path))
            if not capture.isOpened():
                raise ValueError('This video format could not be read. Try MP4.')
            total = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            count = 0
            while True:
                ok, frame = await run(capture.read)
                if not ok:
                    break
                result = await run(analyze, engine, frame)
                count += 1
                result['progress'] = min(1, count / total) if total > 0 else None
                await ws.send_json(result)
                # Browser acknowledgement bounds the output queue and notices cancellation.
                if await asyncio.wait_for(ws.receive_text(), 60) != 'ack':
                    raise ValueError('Invalid acknowledgement')
            if not count:
                raise ValueError('The video contains no readable frames')
            await ws.send_json({'type': 'complete', 'frames': count})
        else:
            while True:
                data = await asyncio.wait_for(ws.receive_bytes(), 60)
                if not 0 < len(data) <= MAX_FRAME:
                    raise ValueError('Camera frame is too large')
                frame = await run(cv2.imdecode, np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                await ws.send_json(await run(analyze, engine, frame))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            message = str(exc) if isinstance(exc, ValueError) else 'Analysis failed. Check server logs and model installation.'
            if not isinstance(exc, ValueError):
                import logging
                logging.exception('Analysis session failed')
            await ws.send_json({'type': 'error', 'message': message})
        except (RuntimeError, WebSocketDisconnect):
            pass
    finally:
        # Resource access stays on the session worker, as does all model inference.
        def cleanup():
            if capture is not None:
                capture.release()
            if engine is not None:
                engine.estimator.pose.close()
        with anyio.CancelScope(shield=True):
            try:
                await run(cleanup)
            finally:
                executor.shutdown(wait=False)
                if path is not None:
                    path.unlink(missing_ok=True)
                if acquired:
                    slots.release()
            try:
                await ws.close()
            except RuntimeError:
                pass
