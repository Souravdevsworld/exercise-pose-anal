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

## Repairing the reported live-camera startup error

The error `pose_exercise_analyzer.py:229: SyntaxError` with an incomplete `log=` is from an edited local analyzer. The reviewed original in Git is valid and remains unchanged. Stop the server with Ctrl+C, update this branch, then run:

```powershell
.\.venv\Scripts\python.exe scripts/repair_analyzer.py
.\.venv\Scripts\python.exe run_server.py
```

The repair reads the exact reviewed original Git blob, verifies its identity and syntax, and preserves an altered local analyzer in a timestamped backup before restoring it. It does not guess a value for `log=` or remove arbitrary lines. Re-running it on the original makes no changes. It needs the Git history from this repository (`git fetch origin` if necessary).

The launcher checks Python syntax and the reference profile before starting. Direct `uvicorn server:app` startup also runs source/reference checks during application startup. Model loading still occurs per session; startup checks do not certify model availability or customer capacity.

Reliability fixes include validation before allocating models, rejecting malformed camera messages and cross-origin browser connections, allowing native initialization/inference to finish before cancellation cleanup, ensuring capacity is returned even if temporary-file cleanup fails, and preventing callbacks from an old browser session from ending a new session. The automated suite now includes regression coverage for syntax failure, repair backups, malformed inputs, session isolation, and disconnect during initialization. CI runs syntax, transport/reference tests, and JavaScript syntax checks without downloading models.

This remains a private pilot implementation. Customer deployment requires authentication/authorization at the application or trusted gateway, shared limits across server processes, capacity/load tests on the target host, and browser/device validation. The process-local session cap is not a distributed customer quota. No claim of enterprise production readiness is made.

Latest verification: **21 tests passed**; Python and JavaScript syntax checks passed; a real YOLO/MediaPipe live-mode WebSocket smoke test using a frame from the supplied video returned a detected pose, annotated image, and reference-comparison status. This tests the live transport with real inference, not physical webcam permissions or browser/device behavior.

## Session summary and recommendations

Uploaded videos generate a report automatically when processing finishes. For live analysis, select **End & generate report**; the current frame finishes, camera capture stops, and the server returns the session summary. Stopping an uploaded video also produces a partial report. An analysis error after at least one processed frame returns an interrupted report when the connection remains available. Closing the browser or losing the connection cannot deliver a final report.

The report appears below the metrics and includes counted vs compared repetitions, tracked-frame coverage, mean elbow-motion differences, recurring top/bottom range differences, and the original analyzer's body-alignment or knee-bend cues. Each observation includes measured evidence and a specific suggestion. Empty or incompletely tracked sessions explicitly state that reference feedback is insufficient. Repeated frame messages do not double-count the last compared repetition.

Choose **Download report** for a text report, **Export JSON** for structured data, or **Print / PDF** to use the browser's print-to-PDF function. Reports remain in that browser page until a new session starts or the page closes; no report history or customer data is stored on the server. Download anything you want to retain before starting another session.

This uses deterministic rules over the existing engine and reference measurements, not an external AI service. Reference thresholds remain the documented 10° heuristics. A difference from one reference is not automatically incorrect technique. The report cannot evaluate hand placement, shoulder mechanics, or overall form, and does not infer injury risk, diagnose conditions, or prescribe medical rehabilitation. Frame-based alignment observations are not rep-level error percentages or durations.

Validation for reports: **29 Python tests and two JavaScript UI tests pass**, plus Python/JavaScript syntax and diff checks. UI tests simulate browser controls; physical webcam and print-dialog behavior still require browser/device testing. The original pose analyzer remains unchanged.
