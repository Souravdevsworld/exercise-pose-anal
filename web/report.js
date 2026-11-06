let sessionReport = null;
function resetReport() {
  sessionReport = null;
  document.getElementById('reportPanel').hidden = true;
}
function reportText(report) {
  const s = report.statistics;
  const parts = ['MOTIONLAB SESSION REPORT', `Exercise: ${report.exercise} | Input: ${report.mode}`, `Created: ${report.created_at} | Outcome: ${report.outcome}`, '', report.summary, '', `Repetitions counted: ${s.counted_reps}`, `Repetitions compared: ${s.compared_reps}`, `Pose tracking: ${s.tracked_frames}/${s.frames} frames (${s.tracking_percent}%)`];
  if (s.mean_elbow_difference_deg !== null) parts.push(`Mean elbow-angle difference: ${s.mean_elbow_difference_deg}°`, `Mean bottom difference: ${s.mean_bottom_difference_deg}°`, `Mean top difference: ${s.mean_top_difference_deg}°`);
  for (const item of report.observations) parts.push('', item.title, item.observation, `What to change: ${item.suggestion}`);
  parts.push('', 'INTERPRETATION', ...report.limitations.map(line => `• ${line}`));
  return parts.join('\n');
}
function showReport(report) {
  sessionReport = report;
  const s = report.statistics;
  document.getElementById('reportMeta').textContent = `${report.exercise === 'pushup' ? 'Push-ups' : 'Sit-ups'} · ${report.mode} · ${report.outcome} · ${new Date(report.created_at).toLocaleString()}`;
  document.getElementById('reportSummary').textContent = report.summary;
  let stats = `${s.counted_reps} reps counted · ${s.compared_reps} compared · ${s.tracked_frames}/${s.frames} frames tracked (${s.tracking_percent}%)`;
  if (s.mean_elbow_difference_deg !== null) stats += ` · Mean elbow-angle difference: ${s.mean_elbow_difference_deg}°`;
  document.getElementById('reportStats').textContent = stats;
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
