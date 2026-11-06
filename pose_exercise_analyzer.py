
'''
 * ===============================================
 * Hackinnovision 26
 * ===============================================
'''
# Team ID:          []
# Filename:         pose_exercise_analyzer.py
# Functions used:   calculate_angle, select_exercise, select_side, render, encode_jpeg,
#                   stream_frames, run_gui, main,
#                   PersonDetector.detect, PoseEstimator.estimate,
#                   BaseAnalyzer.smooth, PushupAnalyzer.update, SitupAnalyzer.update,
#                   ExerciseEngine.process_frame, ExerciseEngine.reset
#
# Nodes (if any for ros2 integration): [exercise_analyzer_node]
# Publishing Topics  - [/exercise/rep_count (std_msgs/Int32),
#                       /exercise/feedback (std_msgs/String),
#                       /exercise/result_json (std_msgs/String),
#                       /exercise/annotated_image (sensor_msgs/Image)]
# Subscribing Topics - [/camera/image_raw (sensor_msgs/Image),
#                       /exercise/select (std_msgs/String),
#                       /exercise/reset (std_msgs/Empty)]
################### IMPORT MODULES #######################
import sys
import time
from dataclasses import dataclass, asdict
from typing import Dict, Generator, List, Optional, Tuple

import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO

mp_pose = mp.solutions.pose

EXERCISES = {"1": "pushup", "2": "situp"}
SIDES = {
    "left": [11, 13, 15, 23, 25, 27],
    "right": [12, 14, 16, 24, 26, 28],
}
JOINT_NAMES = ["shoulder", "elbow", "wrist", "hip", "knee", "ankle"]


def calculate_angle(a, b, c) -> float:
    ba = np.array(a, dtype=float) - np.array(b, dtype=float)
    bc = np.array(c, dtype=float) - np.array(b, dtype=float)
    cosine = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-9)
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


def select_exercise() -> str:
    print("Select the exercise to analyze:")
    for key, name in EXERCISES.items():
        print(f"  {key}. {name.capitalize()}")
    while True:
        choice = input("Enter choice (1/2): ").strip()
        if choice in EXERCISES:
            return EXERCISES[choice]
        print("Invalid choice, try again.")


def select_side(landmarks: List[Tuple[float, float, float]]) -> Dict[str, Tuple[float, float]]:
    scores = {side: sum(landmarks[i][2] for i in idx) for side, idx in SIDES.items()}
    best = SIDES[max(scores, key=scores.get)]
    return {name: landmarks[i][:2] for name, i in zip(JOINT_NAMES, best)}


@dataclass
class AnalysisResult:
    exercise: str
    reps: int
    stage: str
    angle: float
    feedback: str
    person_detected: bool
    timestamp: float

    def to_dict(self) -> dict:
        return asdict(self)


class PersonDetector:
    def __init__(self, weights: str = "yolov8n.pt", confidence: float = 0.5):
        self.model = YOLO(weights)
        self.confidence = confidence

    def detect(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        result = self.model(frame, classes=[0], conf=self.confidence, verbose=False)[0]
        if len(result.boxes) == 0:
            return None
        boxes = result.boxes.xyxy.cpu().numpy()
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        return tuple(int(v) for v in boxes[int(np.argmax(areas))])


class PoseEstimator:
    def __init__(self):
        self.pose = mp_pose.Pose(
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def estimate(self, frame: np.ndarray, box: Tuple[int, int, int, int],
                 margin: float = 0.1) -> Optional[List[Tuple[float, float, float]]]:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = box
        mx, my = int((x2 - x1) * margin), int((y2 - y1) * margin)
        x1, y1 = max(0, x1 - mx), max(0, y1 - my)
        x2, y2 = min(w, x2 + mx), min(h, y2 + my)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        result = self.pose.process(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        if not result.pose_landmarks:
            return None
        cw, ch = x2 - x1, y2 - y1
        return [(x1 + lm.x * cw, y1 + lm.y * ch, lm.visibility)
                for lm in result.pose_landmarks.landmark]


class BaseAnalyzer:
    name = ""

    def __init__(self):
        self.reps = 0
        self.stage = "ready"
        self.angle = 0.0
        self.feedback = "Get in position"
        self._ema = None

    def smooth(self, value: float, alpha: float = 0.4) -> float:
        self._ema = value if self._ema is None else alpha * value + (1 - alpha) * self._ema
        return self._ema

    def update(self, joints: Dict[str, Tuple[float, float]]) -> None:
        raise NotImplementedError


class PushupAnalyzer(BaseAnalyzer):
    name = "pushup"
    DOWN_ANGLE = 90
    UP_ANGLE = 160
    ALIGN_ANGLE = 150

    def update(self, joints):
        elbow = self.smooth(calculate_angle(joints["shoulder"], joints["elbow"], joints["wrist"]))
        body = calculate_angle(joints["shoulder"], joints["hip"], joints["ankle"])
        self.angle = elbow
        if elbow > self.UP_ANGLE:
            if self.stage == "down":
                self.reps += 1
            self.stage = "up"
        elif elbow < self.DOWN_ANGLE:
            self.stage = "down"
        self.feedback = "Keep your body straight" if body < self.ALIGN_ANGLE else "Good form"


class SitupAnalyzer(BaseAnalyzer):
    name = "situp"
    LYING_ANGLE = 130
    SITTING_ANGLE = 75
    KNEE_LIMIT = 130

    def update(self, joints):
        hip = self.smooth(calculate_angle(joints["shoulder"], joints["hip"], joints["knee"]))
        knee = calculate_angle(joints["hip"], joints["knee"], joints["ankle"])
        self.angle = hip
        if hip > self.LYING_ANGLE:
            self.stage = "down"
        elif hip < self.SITTING_ANGLE and self.stage == "down":
            self.stage = "up"
            self.reps += 1
        self.feedback = "Bend your knees more" if knee > self.KNEE_LIMIT else "Good form"


ANALYZERS = {"pushup": PushupAnalyzer, "situp": SitupAnalyzer}


def render(frame, box, landmarks, result: AnalysisResult) -> None:
    if box:
        cv2.rectangle(frame, box[:2], box[2:], (255, 128, 0), 2)
    if landmarks:
        for a, b in mp_pose.POSE_CONNECTIONS:
            if landmarks[a][2] > 0.5 and landmarks[b][2] > 0.5:
                pa = (int(landmarks[a][0]), int(landmarks[a][1]))
                pb = (int(landmarks[b][0]), int(landmarks[b][1]))
                cv2.line(frame, pa, pb, (0, 255, 0), 2)
        for x, y, v in landmarks:
            if v > 0.5:
                cv2.circle(frame, (int(x), int(y)), 4, (0, 0, 255), -1)
    lines = [
        f"{result.exercise.upper()}  Reps: {result.reps}",
        f"Stage: {result.stage}  Angle: {result.angle:.0f}",
        result.feedback,
    ]
    for i, text in enumerate(lines):
        cv2.putText(frame, text, (10, 30 + 30 * i), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 255, 255), 2)


class ExerciseEngine:
    def __init__(self, exercise: str):
        self.exercise = exercise
        self.detector = PersonDetector()
        self.estimator = PoseEstimator()
        self.analyzer = ANALYZERS[exercise]()

    def reset(self) -> None:
        self.analyzer = ANALYZERS[self.exercise]()

    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, AnalysisResult]:
        annotated = frame.copy()
        box = self.detector.detect(frame)
        landmarks = self.estimator.estimate(frame, box) if box else None
        if landmarks:
            self.analyzer.update(select_side(landmarks))
        else:
            self.analyzer.feedback = "No person detected"
        result = AnalysisResult(
            exercise=self.exercise,
            reps=self.analyzer.reps,
            stage=self.analyzer.stage,
            angle=float(self.analyzer.angle),
            feedback=self.analyzer.feedback,
            person_detected=landmarks is not None,
            timestamp=time.time(),
        )
        render(annotated, box, landmarks, result)
        return annotated, result


def encode_jpeg(frame: np.ndarray, quality: int = 80) -> bytes:
    ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buffer.tobytes() if ok else b""


def stream_frames(engine: ExerciseEngine, source) -> Generator[Tuple[np.ndarray, AnalysisResult], None, None]:
    cap = cv2.VideoCapture(source)
    try:
        while cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                break
            yield engine.process_frame(frame)
    finally:
        cap.release()


def run_gui(engine: ExerciseEngine, source) -> None:
    stream = stream_frames(engine, source)
    try:
        for frame, _ in stream:
            cv2.imshow("Exercise Analyzer", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("r"):
                engine.reset()
    finally:
        stream.close()
        cv2.destroyAllWindows()


def main() -> None:
    exercise = select_exercise()
    source = sys.argv[1] if len(sys.argv) > 1 else 0
    if isinstance(source, str) and source.isdigit():
        source = int(source)
    engine = ExerciseEngine(exercise)
    run_gui(engine, source)


if __name__ == "__main__":
    main()