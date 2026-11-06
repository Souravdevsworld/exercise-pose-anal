"""Reference-based elbow-motion comparison. No pose-network training or form score."""
import json
import math
from pathlib import Path
from statistics import median

PROFILE_PATH = Path(__file__).parent / 'reference' / 'pushup_profile.json'


def resample(values, count=32):
    if len(values) < 2:
        raise ValueError('At least two samples are required')
    out = []
    for i in range(count):
        position = i * (len(values) - 1) / (count - 1)
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        out.append(values[lower] + (values[upper] - values[lower]) * (position - lower))
    return out


def normalize_cycle(values):
    bottom = values.index(min(values))
    if bottom < 2 or bottom > len(values) - 3:
        raise ValueError('Incomplete descent or ascent')
    # Align top -> bottom -> top; tempo and the relative phase durations may differ.
    return resample(values[:bottom+1]) + resample(values[bottom:])[1:]


class CycleCollector:
    def __init__(self):
        self.values = []
        self.last_stage = None
        self.last_reps = None
        self.armed = False

    def update(self, result):
        if not result.person_detected or not math.isfinite(result.angle):
            self.values = []
            self.armed = False
            self.last_stage = None
            self.last_reps = result.reps
            return None
        complete = None
        if result.stage == 'up' and result.angle > 160 and not self.armed:
            self.armed = True
            self.values = [float(result.angle)]
        elif self.armed:
            # Retain only the last top frame before descending, avoiding idle padding.
            if result.stage == 'up' and self.last_stage == 'up' and result.angle > 160 and result.angle >= self.values[-1]:
                self.values = [float(result.angle)]
            else:
                self.values.append(float(result.angle))
            if self.last_reps is not None and result.reps > self.last_reps:
                try:
                    curve = normalize_cycle(self.values)
                    complete = {'curve': curve, 'bottom': min(self.values),
                                'top': max(self.values)}
                except ValueError:
                    pass
                self.values = [float(result.angle)]
            if len(self.values) > 3600:
                # Bound stalled sessions; require a fresh top position to re-arm.
                self.values = []
                self.armed = False
        self.last_stage, self.last_reps = result.stage, result.reps
        return complete


def build_profile(results, source):
    collector = CycleCollector()
    cycles = []
    detected, total = 0, 0
    for result in results:
        total += 1
        detected += bool(result.person_detected)
        cycle = collector.update(result)
        if cycle:
            cycles.append(cycle)
    if not total or detected / total < .8:
        raise ValueError('Reference pose coverage is below 80%; choose a clearer clip')
    if len(cycles) < 2:
        raise ValueError('Reference needs at least two fully tracked top-bottom-top repetitions')
    return {'version': 1, 'exercise': 'pushup', 'feature': 'smoothed_elbow_angle_degrees',
            'source': source, 'frames': total, 'detected_frames': detected,
            'complete_cycles': len(cycles), 'bottom': median(c['bottom'] for c in cycles),
            'top': median(c['top'] for c in cycles),
            'curve': [median(c['curve'][i] for c in cycles) for i in range(63)],
            'method': 'median cycle; descent/ascent resampled separately to 32 points'}


def load_profile(path=PROFILE_PATH):
    profile = json.loads(Path(path).read_text())
    if (profile.get('version') != 1 or profile.get('exercise') != 'pushup'
            or len(profile.get('curve', [])) != 63
            or not all(isinstance(x, (float, int)) and math.isfinite(x)
                       for x in profile['curve'])):
        raise ValueError('Invalid push-up reference profile; regenerate it')
    for key in ('bottom', 'top'):
        if not isinstance(profile.get(key), (float, int)) or not math.isfinite(profile[key]):
            raise ValueError('Invalid reference angle')
    return profile


class ReferenceEngine:
    """Session-local comparison state; underlying engine still performs all inference."""
    def __init__(self, engine, profile):
        self.engine = engine
        self.estimator = engine.estimator
        self.profile = profile
        self.collector = CycleCollector()
        self.compared = 0
        self.comparison = {'status': 'waiting', 'message': 'Complete a full push-up from the top to compare.'}

    def process_frame(self, frame):
        annotated, result = self.engine.process_frame(frame)
        cycle = self.collector.update(result)
        if not result.person_detected:
            self.comparison = {'status': 'tracking_lost', 'message': 'Pose lost. Return to the top to start a new comparison.'}
        elif cycle:
            self.compared += 1
            error = sum(abs(a-b) for a, b in zip(cycle['curve'], self.profile['curve'])) / 63
            bottom_delta = cycle['bottom'] - self.profile['bottom']
            top_delta = cycle['top'] - self.profile['top']
            # 10 degrees is a display heuristic, not a clinically validated cutoff.
            if bottom_delta > 10:
                cue = 'Less elbow bend at the bottom than the reference.'
            elif top_delta < -10:
                cue = 'Less elbow extension at the top than the reference.'
            else:
                cue = 'Elbow range is close to the reference.'
            self.comparison = {'status': 'compared', 'compared_reps': self.compared,
                               'mean_angle_difference': round(error, 1),
                               'bottom_difference': round(bottom_delta, 1),
                               'top_difference': round(top_delta, 1), 'message': cue}
        elif self.comparison['status'] == 'tracking_lost':
            self.comparison = {'status': 'waiting', 'message': 'Complete a new full repetition from the top.'}
        return annotated, result
