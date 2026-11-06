# Motionlab exercise analysis

Responsive website for uploaded video and live webcam analysis, wrapping the existing `pose_exercise_analyzer.py` without changing it.

## Windows setup (Python 3.12)

Run inside this repository in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000. Choose push-ups or sit-ups, select a video or live camera, and start analysis. End session cancels processing; starting again creates a fresh analyzer. First inference initializes YOLO and may download `yolov8n.pt`; provision that file in the working directory for offline operation. MediaPipe 0.10.21 is pinned because the existing analyzer uses `mp.solutions.pose`.

## How it works

- Same-origin FastAPI serves the UI and `/ws/analyze` WebSocket.
- Each connection creates its own `ExerciseEngine(exercise)` on a dedicated single-thread worker. No shared rep counter, pose tracker, detector, or analyzer. This is anonymous session isolation, not an account/login system.
- All exercise inference uses **only `engine.process_frame(frame)`**. No duplicated exercise logic or calls to reset, stream, GUI, or analyzer updates. Direct pose `close()` is used only to release native resources at session end.
- Live mode sends one JPEG at a time and waits for its result. The browser camera closes on stop/disconnect/navigation.
- Upload mode sends a video in bounded chunks (100 MB maximum), decodes every frame in order with OpenCV, and returns annotated JPEGs and metrics. Playback follows inference speed, not original video speed. Uploaded audio is not played. Stop cancels the session; temporary files are deleted when the session exits.
- Images are bounded to a 1280-pixel maximum edge before inference. The UI displays engine reps, angle, stage, detection status, and feedback; it invents no form scores.
- At most four concurrent sessions per process are admitted. Independent YOLO instances consume substantial RAM; reduce `MAX_SESSIONS` for smaller machines. Use one server worker for this process-local cap.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Transport tests use a fake engine to verify independent session state, per-frame calls, cleanup, invalid data, upload limits, and processing all uploaded frames. They do not establish real-model accuracy. Manually test known push-up and sit-up footage and two browser sessions with the actual models.

## Hosting

Deploy the complete Python application on a Python/container host with sufficient RAM, WebSocket support, writable temporary storage, and model dependencies. It cannot run on static hosting or a Cloudflare Worker alone. HTTPS is required for camera access except on localhost. Configure a reverse proxy to allow WebSocket upgrades and long inference sessions. This MVP has no account authentication or distributed quotas; keep it private for testing before exposing a public inference endpoint.

## Existing engine review

The engine selects the largest detected person, so frame only one athlete. It supports push-ups and sit-ups only. Angle thresholds are fixed, and reps persist across brief pose loss within a session. A single RGB camera produces 2D estimates; occlusion and viewing angle affect feedback. These behaviors are preserved exactly. The UI labels elapsed analysis time separately from video duration.
