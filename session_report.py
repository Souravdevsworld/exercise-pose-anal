"""Deterministic session summaries from measured results, with session-local state."""
from datetime import datetime, timezone


class SessionReport:
    def __init__(self, exercise, mode):
        self.exercise, self.mode = exercise, mode
        self.frames = self.detected = self.reps = 0
        self.alignment_frames = self.knee_frames = 0
        self.compared = 0
        self.error_sum = self.bottom_sum = self.top_sum = 0.0
        self.shallow = self.extension = self.deeper = 0
        self.last_comparison = 0

    def update(self, result, comparison=None):
        self.frames += 1
        self.reps = max(self.reps, result.reps)
        if result.person_detected:
            self.detected += 1
            self.alignment_frames += result.feedback == 'Keep your body straight'
            self.knee_frames += result.feedback == 'Bend your knees more'
        # A comparison remains in frame messages until the next rep. Count it once.
        if comparison and comparison.get('status') == 'compared':
            number = comparison['compared_reps']
            if number > self.last_comparison:
                self.last_comparison = number
                self.compared += 1
                self.error_sum += comparison['mean_angle_difference']
                self.bottom_sum += comparison['bottom_difference']
                self.top_sum += comparison['top_difference']
                self.shallow += comparison['bottom_difference'] > 10
                self.extension += comparison['top_difference'] < -10
                self.deeper += comparison['bottom_difference'] < -10

    def build(self, outcome='completed'):
        coverage = round(100*self.detected/self.frames, 1) if self.frames else 0
        issues = []
        def issue(title, observation, change):
            issues.append({'title': title, 'observation': observation, 'suggestion': change})
        if self.frames and coverage < 80:
            issue('Improve tracking before judging technique',
                  f'Pose tracked in {self.detected} of {self.frames} frames ({coverage}%).',
                  'Use a stable side-on camera, good lighting, and keep your full body visible; record another set.')
        if self.shallow:
            issue('Less elbow bend at the bottom',
                  f'{self.shallow} of {self.compared} compared reps had a bottom elbow angle more than 10° above the reference.',
                  'Review your lowering phase beside the reference. Aim for a controlled, comfortable range; do not force the reference depth.')
        if self.extension:
            issue('Less elbow extension at the top',
                  f'{self.extension} of {self.compared} compared reps finished more than 10° below the reference top angle.',
                  'Finish the upward phase with controlled elbow extension within your comfortable range; avoid forcefully locking the elbows.')
        if self.deeper:
            issue('More elbow bend than the reference',
                  f'{self.deeper} of {self.compared} compared reps went more than 10° below the reference bottom angle.',
                  'Check that your camera view matches the reference. This difference alone does not establish an error or require a deeper movement.')
        if self.alignment_frames:
            issue('Body-alignment cue appeared',
                  f'The analyzer requested a straighter body in {self.alignment_frames} of {self.detected} tracked frames.',
                  'Review whether your shoulders, hips, and ankles stay aligned. Keep your trunk controlled; the available result cannot distinguish hip sag from raised hips.')
        if self.knee_frames:
            issue('Knee-bend cue appeared',
                  f'The analyzer requested more knee bend in {self.knee_frames} of {self.detected} tracked frames.',
                  'Review your knee position during sit-ups and use a comfortable, controlled bend.')
        if self.exercise == 'pushup' and not self.compared:
            issue('Not enough data for reference feedback',
                  'No fully tracked top–bottom–top repetition was available for comparison.',
                  'Start at the top and complete a full repetition with your entire body visible. Partial or interrupted repetitions cannot be compared.')
        if not self.frames:
            summary = 'No frames were analyzed. Record or upload a session to generate technique feedback.'
        elif self.exercise == 'pushup' and not self.compared:
            summary = f'{self.reps} reps counted, but no complete repetition could be compared reliably.'
        elif issues:
            summary = f'{self.reps} reps counted. Review the observations below before your next set.'
        else:
            summary = 'No tracked issues were flagged in this session. This does not establish that your overall technique is correct.'
        stats = {'frames':self.frames, 'tracked_frames':self.detected, 'tracking_percent':coverage,
                 'counted_reps':self.reps, 'compared_reps':self.compared,
                 'mean_elbow_difference_deg':round(self.error_sum/self.compared,1) if self.compared else None,
                 'mean_bottom_difference_deg':round(self.bottom_sum/self.compared,1) if self.compared else None,
                 'mean_top_difference_deg':round(self.top_sum/self.compared,1) if self.compared else None}
        return {'version':1, 'created_at':datetime.now(timezone.utc).isoformat(),
                'exercise':self.exercise, 'mode':self.mode, 'outcome':outcome,
                'summary':summary, 'statistics':stats, 'observations':issues,
                'limitations':[
                    'Reference comparison measures elbow motion only. It cannot evaluate hand placement, shoulder mechanics, or complete body technique.',
                    '10° flags are engineering heuristics, not validated technique or medical thresholds. Camera perspective can change measurements.',
                    'Body alignment and knee observations come from the existing analyzer; frame counts are not durations or percentages of incorrect repetitions.',
                    'Interrupted or partial repetitions may be counted by the engine but are excluded from reference comparison.',
                    'This is automated technique feedback, not a medical assessment. Stop exercising if you experience pain.'
                ]}
