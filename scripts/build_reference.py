"""Extract a reproducible motion template using the existing engine's process_frame."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reference_comparison import build_profile


def main():
    import cv2
    from pose_exercise_analyzer import ExerciseEngine
    parser = argparse.ArgumentParser()
    parser.add_argument('video', type=Path)
    parser.add_argument('--output', type=Path, default=Path('reference/pushup_profile.json'))
    args = parser.parse_args()
    source = {'filename': args.video.name,
              'sha256': hashlib.sha256(args.video.read_bytes()).hexdigest()}
    engine = ExerciseEngine('pushup')
    cap = cv2.VideoCapture(str(args.video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    def results():
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            height, width = frame.shape[:2]
            if max(height, width) > 1280:
                frame = cv2.resize(frame, (round(width*1280/max(height,width)), round(height*1280/max(height,width))))
            _, result = engine.process_frame(frame)
            yield result
    try:
        profile = build_profile(results(), source)
    finally:
        cap.release()
        engine.estimator.pose.close()
    profile['source_fps'] = fps
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, indent=2) + '\n')
    print(f"Saved {args.output}: {profile['complete_cycles']} full cycles, "
          f"{profile['detected_frames']}/{profile['frames']} frames tracked")

if __name__ == '__main__':
    main()
