from types import SimpleNamespace as NS
from session_report import SessionReport


def result(reps=1, detected=True, feedback='Good form'):
    return NS(reps=reps, person_detected=detected, feedback=feedback)


def compared(rep=1, bottom=15, top=-12):
    return {'status':'compared','compared_reps':rep, 'mean_angle_difference':17,
            'bottom_difference':bottom, 'top_difference':top}


def test_comparisons_count_once_and_are_session_local():
    a, b = SessionReport('pushup','live'), SessionReport('pushup','live')
    for _ in range(20):
        a.update(result(), compared())
    report = a.build()
    assert report['statistics']['compared_reps'] == 1
    assert report['statistics']['mean_elbow_difference_deg'] == 17
    titles = [i['title'] for i in report['observations']]
    assert 'Less elbow bend at the bottom' in titles
    assert 'Less elbow extension at the top' in titles
    assert b.build()['statistics']['frames'] == 0


def test_empty_partial_and_tracking_loss_have_no_false_good_form():
    r = SessionReport('pushup','upload')
    assert 'No frames' in r.build()['summary']
    r.update(result(detected=False))
    report = r.build('interrupted')
    assert report['outcome'] == 'interrupted'
    assert report['statistics']['mean_elbow_difference_deg'] is None
    assert 'no complete' in report['summary']
    assert len(report['observations']) == 2


def test_alignment_and_knees_only_count_tracked_frames():
    r = SessionReport('situp','upload')
    r.update(result(feedback='Bend your knees more'))
    r.update(result(detected=False, feedback='Bend your knees more'))
    assert r.knee_frames == 1
    r.update(result(feedback='Keep your body straight'))
    report = r.build()
    assert report['statistics']['tracked_frames'] == 2
    assert report['statistics']['compared_reps'] == 0
    assert any(i['title']=='Body-alignment cue appeared' for i in report['observations'])


def test_matching_reference_not_certified_as_correct():
    r = SessionReport('pushup','upload')
    r.update(result(), compared(bottom=0,top=0))
    report = r.build()
    assert not report['observations']
    assert 'does not establish' in report['summary']


def test_signed_differences_do_not_cancel_issue_counts():
    r = SessionReport('pushup','upload')
    r.update(result(), compared(1,bottom=20,top=0))
    r.update(result(2), compared(2,bottom=-20,top=0))
    report = r.build()
    assert report['statistics']['mean_bottom_difference_deg'] == 0
    assert len(report['observations']) == 2
