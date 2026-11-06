let sessionReport = null;
function resetReport() {
  sessionReport = null;
  document.getElementById('reportPanel').hidden = true;
}
function reportText(report) {
  const s = report.statistics;
  const parts = ['MOTIONLAB SESSION REPORT', `Exercise: ${report.exercise} | Input: ${report.mode}`, `Created: ${report.created_at} | Outcome: ${report.outcome}`, '', report.summary, '', `Repetitions counted: ${s.counted_reps}`, `Repetitions compared: ${s.compared_reps}`, `Pose tracking: ${s.tracked_frames}/${s.frames} frames (${s.tracking_percent}%)`];
  if (s.mean_elbow_difference_deg !== null) parts.push(`Mean elbow-angle difference: ${s.mean_elbow_difference_deg}°`, `Mean bottom difference: ${s.mean_bottom_difference_deg}°`, `Mean top difference: ${s.mean_top_difference_deg}°`);
  parts.push('', 'WHAT THE MEASUREMENTS SHOW', ...(report.insights || []));
  if (report.reference) parts.push(`Reference: ${report.reference.source}; bottom ${report.reference.bottom_angle}°; top ${report.reference.top_angle}°`);
  if (report.repetitions?.length) {
    parts.push('', 'REPETITION BREAKDOWN (degrees; end frame is a processed-frame index)');
    for (const r of report.repetitions) parts.push(`Rep ${r.rep} | End frame ${r.end_frame} | Mean difference ${r.mean_difference_deg}° | Lowering ${angle(r.lowering_difference_deg)} | Rising ${angle(r.rising_difference_deg)} | Bottom ${angle(r.bottom_angle_deg)} (${signed(r.bottom_difference_deg)}) | Top ${angle(r.top_angle_deg)} (${signed(r.top_difference_deg)}) | ${r.range_note}`);
  }
  if (report.rep_rows_truncated) parts.push('Only the first 500 compared reps are listed; session statistics cover all compared reps.');
  parts.push('', 'NEXT-SET FOCUS', ...(report.next_set_focus || []));
  for (const item of report.observations) parts.push('', item.title, item.observation, `What to change: ${item.suggestion}`);
  parts.push('', 'INTERPRETATION', ...report.limitations.map(line => `• ${line}`));
  return parts.join('\n');
}
function angle(value) { return value == null ? '—' : `${value}°`; }
function signed(value) { return value == null ? '—' : `${value > 0 ? '+' : ''}${value}°`; }
function fillList(id, values) {
  const parent = document.getElementById(id); parent.replaceChildren();
  for (const text of values) { const li = document.createElement('li'); li.textContent = text; parent.append(li); }
}
function renderRepTable(report) {
  const container = document.getElementById('reportRepTable'); container.replaceChildren();
  if (!report.repetitions?.length) { container.textContent = 'No complete compared repetitions are available. Partial repetitions cannot support this breakdown.'; return; }
  container.textContent = '';
  const table = document.createElement('table');
  const caption = document.createElement('caption'); caption.textContent = 'Elbow angles in degrees. Parentheses show signed differences from the reference. Positive bottom difference means less elbow bend. End frame is a processed-frame index, not a timestamp.'; table.append(caption);
  const head = document.createElement('thead'), header = document.createElement('tr');
  for (const title of ['Counted rep', 'End frame', 'Mean difference', 'Lowering difference', 'Rising difference', 'Bottom (difference)', 'Top (difference)', 'Endpoint check']) { const th = document.createElement('th'); th.textContent = title; header.append(th); }
  head.append(header); table.append(head);
  const body = document.createElement('tbody');
  for (const r of report.repetitions) {
    const row = document.createElement('tr');
    for (const text of [r.rep,r.end_frame,angle(r.mean_difference_deg),angle(r.lowering_difference_deg),angle(r.rising_difference_deg),`${angle(r.bottom_angle_deg)} (${signed(r.bottom_difference_deg)})`,`${angle(r.top_angle_deg)} (${signed(r.top_difference_deg)})`,r.range_note]) { const td = document.createElement('td'); td.textContent = String(text); row.append(td); }
    body.append(row);
  }
  table.append(body); container.append(table);
}
function showReport(report) {
  sessionReport = report;
  const s = report.statistics;
  document.getElementById('reportMeta').textContent = `${report.exercise === 'pushup' ? 'Push-ups' : 'Sit-ups'} · ${report.mode} · ${report.outcome} · ${new Date(report.created_at).toLocaleString()}`;
  document.getElementById('reportSummary').textContent = report.summary;
  let stats = `${s.counted_reps} reps counted · ${s.compared_reps} compared · ${s.tracked_frames}/${s.frames} frames tracked (${s.tracking_percent}%)`;
  if (s.mean_elbow_difference_deg !== null) stats += ` · Mean elbow-angle difference: ${s.mean_elbow_difference_deg}°`;
  document.getElementById('reportStats').textContent = stats;
  fillList('reportInsights',report.insights || []);
  fillList('reportFocus',report.next_set_focus || []);
  document.getElementById('reportReference').textContent = report.reference ? `Reference: ${report.reference.source} · Bottom ${report.reference.bottom_angle}° · Top ${report.reference.top_angle}° · ${report.reference.cycles ?? '—'} reference reps` : 'No reference endpoint measurements available for this report.';
  renderRepTable(report);
  document.getElementById('reportRowNote').textContent = report.rep_rows_truncated ? 'First 500 compared repetitions shown; aggregate statistics include every compared repetition.' : '';
  const issues = document.getElementById('reportIssues');
  issues.replaceChildren();
  for (const item of report.observations) {
    const article = document.createElement('article');
    for (const [tag, value] of [['h3',item.title],['p',item.observation],['p',`What to change: ${item.suggestion}`]]) {
      const node = document.createElement(tag); node.textContent = value; article.append(node);
    }
    issues.append(article);
  }
  const limits = document.getElementById('reportLimits');
  limits.replaceChildren();
  for (const text of report.limitations) { const li = document.createElement('li'); li.textContent = text; limits.append(li); }
  document.getElementById('reportPanel').hidden = false;
}
function downloadReport(json) {
  if (!sessionReport) return;
  const content = json ? JSON.stringify(sessionReport,null,2) : reportText(sessionReport);
  const url = URL.createObjectURL(new Blob([content],{type:json?'application/json':'text/plain;charset=utf-8'}));
  const a = document.createElement('a'); a.href=url; a.download=`motionlab-${sessionReport.exercise}-report.${json?'json':'txt'}`;
  document.body.append(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
document.getElementById('downloadReport').onclick = () => downloadReport(false);
document.getElementById('downloadJson').onclick = () => downloadReport(true);
document.getElementById('printReport').onclick = () => {
  const details = document.querySelector('#reportPanel details');
  const wasOpen = details.open; details.open = true;
  try { window.print(); } finally { details.open = wasOpen; }
};
