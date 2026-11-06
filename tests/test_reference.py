from types import SimpleNamespace as NS
import pytest
from reference_comparison import CycleCollector, ReferenceEngine, build_profile, normalize_cycle


def cycle(offset=0, count=1):
    values = [170, 150, 120, 85, 65, 85, 120, 150, 170]
    stage = 'up'
    for i, angle in enumerate(values):
        if angle < 90:
            stage = 'down'
        if angle > 160:
            stage = 'up'
        yield NS(person_detected=True, angle=angle+offset, stage=stage,
                 reps=count if i == len(values)-1 else count-1)


def test_normalized_tempo_invariance():
    a = normalize_cycle([170,140,110,80,60,80,110,140,170])
    b = normalize_cycle([170,155,140,125,110,95,80,70,60,70,80,95,110,125,140,155,170])
    assert sum(abs(x-y) for x,y in zip(a,b))/63 < 2


def test_extract_full_cycles():
    profile = build_profile(list(cycle(count=1))+list(cycle(count=2)), {'filename':'test'})
    assert profile['complete_cycles'] == 2
    assert profile['bottom'] == 65
    assert len(profile['curve']) == 63
    assert profile['curve'][0] == 170


def test_pose_loss_discards_partial():
    collector = CycleCollector()
    results = list(cycle())
    for r in results[:5]:
        collector.update(r)
    collector.update(NS(person_detected=False, angle=0, reps=0))
    assert all(collector.update(r) is None for r in results[5:])


def test_bad_reference_rejected():
    with pytest.raises(ValueError, match='two fully'):
        build_profile(cycle(), {})
    with pytest.raises(ValueError, match='coverage'):
        build_profile([NS(person_detected=False, angle=0, reps=0)], {})


def test_reference_comparison_is_session_local():
    profile = build_profile(list(cycle(count=1))+list(cycle(count=2)), {})
    class Engine:
        estimator = None
        def __init__(self, offset):
            self.results = iter(cycle(offset))
        def process_frame(self, frame):
            return frame, next(self.results)
    a, b = ReferenceEngine(Engine(0), profile), ReferenceEngine(Engine(15), profile)
    for _ in range(9):
        a.process_frame(None)
        b.process_frame(None)
    assert a.comparison['mean_angle_difference'] == 0
    assert b.comparison['bottom_difference'] == 15
    assert b.comparison['mean_angle_difference'] == 15
    assert a.compared == b.compared == 1


def test_invalid_profile(tmp_path):
    import json
    from reference_comparison import load_profile
    file = tmp_path / 'profile.json'
    file.write_text(json.dumps({'version': 1, 'exercise': 'pushup', 'curve': [0]*63,
                                'bottom': float('nan'), 'top': 170}))
    with pytest.raises(ValueError, match='Invalid reference angle'):
        load_profile(file)


def test_initial_partial_rep_is_not_compared():
    collector = CycleCollector()
    results = list(cycle())
    assert all(collector.update(result) is None for result in results[3:])
