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


def test_detailed_rows_actual_endpoints_and_reference():
    r = SessionReport('pushup','upload')
    c = compared(bottom=5, top=-2)
    c.update(bottom_angle=55,top_angle=168,lowering_difference=3,rising_difference=4,
             reference={'bottom_angle':50,'top_angle':170,'source':'reference.mp4','cycles':5})
    r.update(result(), c)
    r.update(result(), c)
    report = r.build('stopped')
    assert report['version'] == 2
    assert len(report['repetitions']) == 1
    row = report['repetitions'][0]
    assert row['bottom_angle_deg'] == 55
    assert row['lowering_difference_deg'] == 3
    assert row['end_frame'] == 1
    assert report['reference']['top_angle'] == 170
    assert any('55.0° / 168.0°' in text for text in report['insights'])
    assert any('processed portion' in text for text in report['insights'])
    assert report['next_set_focus']


def test_consistency_and_review_rep_use_all_reps():
    r = SessionReport('pushup','upload')
    c = compared(1,bottom=1,top=2)
    c['mean_angle_difference'] = 2
    r.update(result(1),c)
    c = compared(2,bottom=9,top=4)
    c['mean_angle_difference'] = 8
    r.update(result(2),c)
    report = r.build()
    assert any('Bottom-angle spread across compared reps: 8°' in text for text in report['insights'])
    assert any('counted rep 1 (2°' in text and 'counted rep 2 (8°' in text for text in report['insights'])
    assert any('All compared repetitions' in text for text in report['insights'])


def test_row_limit_does_not_limit_aggregate_statistics():
    r = SessionReport('pushup','live')
    for i in range(1,503):
        r.update(result(i),compared(i,bottom=0,top=0))
    report = r.build()
    assert len(report['repetitions']) == 500
    assert report['rep_rows_truncated']
    assert report['statistics']['compared_reps'] == 502
