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
        self.rows = []
        self.reference = None
        self.error_min = self.error_max = None
        self.bottom_min = self.bottom_max = None
        self.top_min = self.top_max = None
        self.closest_rep = self.review_rep = None
        self.tracking_breaks = 0
        self.was_detected = None

    def update(self, result, comparison=None):
        self.frames += 1
        if not result.person_detected and self.was_detected is True:
            self.tracking_breaks += 1
        self.was_detected = result.person_detected
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
                error = comparison['mean_angle_difference']
                bottom, top = comparison['bottom_difference'], comparison['top_difference']
                if self.error_min is None or error < self.error_min:
                    self.error_min, self.closest_rep = error, result.reps
                if self.error_max is None or error > self.error_max:
                    self.error_max, self.review_rep = error, result.reps
                self.bottom_min = bottom if self.bottom_min is None else min(self.bottom_min, bottom)
                self.bottom_max = bottom if self.bottom_max is None else max(self.bottom_max, bottom)
                self.top_min = top if self.top_min is None else min(self.top_min, top)
                self.top_max = top if self.top_max is None else max(self.top_max, top)
                if comparison.get('reference'):
                    self.reference = dict(comparison['reference'])
                if len(self.rows) < 500:
                    flags = []
                    if bottom > 10: flags.append('Less bend at bottom')
                    if top < -10: flags.append('Less extension at top')
                    if bottom < -10: flags.append('More bend than reference')
                    self.rows.append({'rep': result.reps, 'end_frame':self.frames,
                        'mean_difference_deg':error,
                        'bottom_angle_deg':comparison.get('bottom_angle'),
                        'top_angle_deg':comparison.get('top_angle'),
                        'bottom_difference_deg':bottom, 'top_difference_deg':top,
                        'lowering_difference_deg':comparison.get('lowering_difference'),
                        'rising_difference_deg':comparison.get('rising_difference'),
                        'range_note':'; '.join(flags) if flags else 'Within the checked endpoint thresholds'})

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
        insights = []
        if self.compared:
            insights.append(f'{self.compared} of {self.reps} counted repetitions were fully tracked and available for elbow-motion comparison.')
            insights.append(f'The mean aligned elbow-angle difference was {stats["mean_elbow_difference_deg"]}°. This is an angle difference, not an accuracy percentage or overall form score.')
            insights.append(f'Closest elbow-motion match: counted rep {self.closest_rep} ({self.error_min}° mean difference). Largest difference: counted rep {self.review_rep} ({self.error_max}°). These labels describe similarity, not safest or best technique.')
            insights.append(f'Bottom-angle spread across compared reps: {round(self.bottom_max-self.bottom_min,1)}°; top-angle spread: {round(self.top_max-self.top_min,1)}°. Smaller spreads indicate more repeatable elbow endpoints, not necessarily better technique.')
            if self.reference:
                insights.append(f'Mean measured bottom / top elbow angles: {round(self.reference["bottom_angle"]+stats["mean_bottom_difference_deg"],1)}° / {round(self.reference["top_angle"]+stats["mean_top_difference_deg"],1)}°. Reference: {self.reference["bottom_angle"]}° / {self.reference["top_angle"]}°.')
            if not self.shallow and not self.extension and not self.deeper:
                insights.append('All compared repetitions stayed within the checked 10° endpoint-difference thresholds. No change to depth or extension is suggested by those checks alone.')
        insights.append(f'Pose tracking was present in {self.detected}/{self.frames} frames, with {self.tracking_breaks} tracked-to-untracked interruptions. Coverage is not a measurement-confidence score.')
        if outcome != 'completed':
            insights.append('This report covers only the processed portion of the session; unprocessed footage is excluded.')
        focus = [item['suggestion'] for item in issues[:3]]
        if not focus and self.compared:
            focus = ['Keep the same side-on camera view so future comparisons are meaningful.',
                     'Aim to repeat your measured elbow range with controlled movement; this report does not justify forcing a new depth.',
                     'Use a separate visual or qualified coaching review for hand placement and shoulder mechanics, which were not assessed.']
        elif not focus:
            focus = ['Record a clear side-on set with your full body visible to obtain enough movement data.']
        return {'version':2, 'created_at':datetime.now(timezone.utc).isoformat(),
                'exercise':self.exercise, 'mode':self.mode, 'outcome':outcome,
                'summary':summary, 'statistics':stats, 'observations':issues,
                'insights':insights, 'next_set_focus':focus, 'reference':self.reference,
                'repetitions':list(self.rows), 'rep_rows_truncated':self.compared > len(self.rows),
                'limitations':[
                    'Reference comparison measures elbow motion only. It cannot evaluate hand placement, shoulder mechanics, or complete body technique.',
                    '10° flags are engineering heuristics, not validated technique or medical thresholds. Camera perspective can change measurements.',
                    'Body alignment and knee observations come from the existing analyzer; frame counts are not durations or percentages of incorrect repetitions.',
                    'Interrupted or partial repetitions may be counted by the engine but are excluded from reference comparison.',
                    'This is automated technique feedback, not a medical assessment. Stop exercising if you experience pain.'
                ]}
