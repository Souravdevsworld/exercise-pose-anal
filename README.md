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

## Push-up reference comparison

The web app now compares each fully tracked push-up against `reference/pushup_profile.json`. This is a calibrated movement template, **not training/fine-tuning YOLO or MediaPipe**. All pose inference still passes through the original, unmodified `ExerciseEngine.process_frame`.

To build or replace the template from the supplied reference video:

```powershell
.\.venv\Scripts\python.exe scripts/build_reference.py "D:\path\videoplayback (5).mp4"
```

The builder reads every frame, requires at least 80% pose coverage and two complete top-bottom-top repetitions, and records the source SHA-256. Initial/final partial repetitions and cycles interrupted by pose loss are discarded. It computes the median elbow-angle curve across valid repetitions, aligning descent and ascent separately. The original smoothed elbow-angle output is used for both reference and user, so feature extraction is consistent.

Each user session owns a separate comparison collector. After a full repetition, upload and live modes display mean aligned elbow-angle difference, bottom-angle difference, and top-angle difference in degrees. Positive bottom difference means less elbow bend than the reference. The 10° cue threshold is an adjustable engineering heuristic; it is not a validated biomechanical threshold. No comparison is produced from a partial repetition, and pose loss requires returning to the top.

The template does not compare body alignment, hand placement, shoulder mechanics, camera angle, or tempo; the existing engine still supplies its own alignment feedback. Match the reference's side-on view. One demonstration is not evidence of universally correct technique. Different camera perspectives and body proportions can affect measurements. Very shallow movements that never meet the original engine's rep thresholds cannot produce a completed-repetition comparison. Sit-ups continue with original analysis only.

The profile is loaded when a push-up session starts. If missing/invalid, the session reports an error rather than substituting invented reference values. Regenerate it and restart the session. The raw reference video is not committed; keep the supplied original if you need to rebuild it.

### Supplied reference extraction result

The supplied `videoplayback (5).mp4` was processed with the real YOLO + MediaPipe engine: **295/295 frames tracked, five full cycles extracted**, 30 fps. The median smoothed bottom/top elbow angles are approximately **47.8° / 172.3°**. These are observations from this demonstration, not prescribed target angles. The generated profile is committed and ready to load; users do not need to rebuild it.

Validation for this change: 13 automated tests passed, JavaScript syntax check passed, real reference extraction succeeded, and the original analyzer's diff is empty. General accuracy on other athletes and camera setups remains unvalidated.
