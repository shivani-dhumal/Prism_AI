HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CodeGuard Pro — AI Audit Report</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Syne:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#060a13;--surface:rgba(19,22,32,0.9);--surface2:#1b1f2e;--border:rgba(37,42,61,0.6);--border2:#2e3450;--text:#e2e8f0;--muted:#8892b0;--accent:#6c8fff;--high:#ff5c5c;--medium:#f59e0b;--low:#38bdf8;--pass:#22c55e;--fp:#c084fc;--high-bg:rgba(255,92,92,.10);--medium-bg:rgba(245,158,11,.10);--low-bg:rgba(56,189,248,.10);--pass-bg:rgba(34,197,94,.08);--fp-bg:rgba(192,132,252,.10)}
*{margin:0;padding:0;box-sizing:border-box}html{scroll-behavior:smooth}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;font-size:13px;line-height:1.6}
.hdr{background:linear-gradient(135deg,rgba(10,12,20,0.95) 0%,rgba(16,20,34,0.95) 40%,rgba(20,26,46,0.95) 100%);border-bottom:1px solid var(--border2);padding:40px 56px 32px;position:relative;overflow:hidden;backdrop-filter:blur(16px)}
.hdr::before{content:'';position:absolute;top:-80px;right:-80px;width:400px;height:400px;background:radial-gradient(circle,rgba(108,143,255,.08) 0%,transparent 70%);pointer-events:none}
.hdr-top{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:20px}
.hdr-title{font-family:'Syne',sans-serif}
.hdr-title h1{font-size:26px;font-weight:800;letter-spacing:-.5px;color:#fff;display:flex;align-items:center;gap:10px}
.hdr-title p{color:var(--muted);font-size:12px;margin-top:6px}
.hdr-title .target{font-family:'IBM Plex Mono',monospace;font-size:11px;color:#6c8fff;background:rgba(108,143,255,.1);border:1px solid rgba(108,143,255,.25);padding:3px 10px;border-radius:4px;display:inline-block;margin-top:8px}
.score-ring-wrap{display:flex;align-items:center;gap:24px}
.score-ring{width:90px;height:90px;position:relative}
.score-ring svg{transform:rotate(-90deg)}
.score-ring .val{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:'Syne',sans-serif;font-size:22px;font-weight:800;color:#fff}
.score-ring .val span{font-size:9px;font-family:'Inter',sans-serif;color:var(--muted);font-weight:500;letter-spacing:.5px;text-transform:uppercase;margin-top:-2px}
.score-meta{font-family:'Syne',sans-serif}.score-meta .risk{font-size:18px;font-weight:700;color:var(--medium)}.score-meta p{font-size:11px;color:var(--muted);margin-top:3px}
.statbar{display:flex;gap:1px;background:var(--border);border-bottom:1px solid var(--border2);overflow-x:auto}
.stat{flex:1;min-width:100px;padding:18px 24px;background:var(--surface);text-align:center;transition:.2s}
.stat:hover{background:var(--surface2)}
.stat .v{font-family:'Syne',sans-serif;font-size:24px;font-weight:800;line-height:1}
.stat .l{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.7px;margin-top:5px}
.stat .v.high{color:var(--high)}.stat .v.med{color:var(--medium)}.stat .v.low{color:var(--low)}.stat .v.fp{color:var(--fp)}.stat .v.pass{color:var(--pass)}.stat .v.neutral{color:var(--accent)}
.main{max-width:1560px;margin:0 auto;padding:32px 56px 64px}
.sec{background:var(--surface);border:1px solid var(--border);border-radius:10px;margin-bottom:24px;overflow:hidden;animation:fadeIn .3s ease both}
.sec-body{overflow-x:auto}
.tabs{display:flex;gap:4px;padding:16px 22px 0;border-bottom:1px solid var(--border);background:var(--surface2);overflow-x:auto}
.tab-btn{padding:8px 18px;border-radius:6px 6px 0 0;font-size:12px;font-weight:600;cursor:pointer;border:1px solid transparent;border-bottom:none;transition:.15s;color:var(--muted);white-space:nowrap;background:none}
.tab-btn.active{background:var(--surface);border-color:var(--border2);color:var(--text)}.tab-btn:hover:not(.active){background:rgba(255,255,255,.04);color:var(--text)}
.tab-pane{display:none}.tab-pane.active{display:block}
.summary-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;padding:24px}
.sum-card{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:18px 20px}
.sum-card h3{font-family:'Syne',sans-serif;font-size:13px;font-weight:700;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.sum-card .bullets{list-style:none;display:flex;flex-direction:column;gap:5px}
.sum-card .bullets li{font-size:12px;color:var(--muted);padding-left:14px;position:relative}
.sum-card .bullets li::before{content:'→';position:absolute;left:0;color:var(--accent);font-size:10px}
table{width:100%;border-collapse:collapse}
th{background:#161a27;text-align:left;padding:10px 16px;font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;border-bottom:2px solid var(--border2);white-space:nowrap;position:sticky;top:0;z-index:1}
td{padding:11px 16px;border-bottom:1px solid var(--border);vertical-align:top}
tr:last-child td{border-bottom:none}tr:hover td{background:rgba(255,255,255,.02)}
.file-cell{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--accent);max-width:200px;word-break:break-all}
.rule-cell{font-size:12px;font-weight:600;color:var(--text)}
.finding-cell{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--muted);max-width:260px;word-break:break-word}
.badge{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;white-space:nowrap}
.b-high{background:var(--high-bg);color:var(--high);border:1px solid rgba(255,92,92,.3)}
.b-medium{background:var(--medium-bg);color:var(--medium);border:1px solid rgba(245,158,11,.3)}
.b-low{background:var(--low-bg);color:var(--low);border:1px solid rgba(56,189,248,.3)}
.b-fp{background:var(--fp-bg);color:var(--fp);border:1px solid rgba(192,132,252,.3)}
.b-pass{background:var(--pass-bg);color:var(--pass);border:1px solid rgba(34,197,94,.3)}
.b-info{background:rgba(108,143,255,.1);color:var(--accent);border:1px solid rgba(108,143,255,.3)}
.rec-cell{max-width:380px;font-size:12px;line-height:1.65;color:var(--text)}
.rec-cell code{font-family:'IBM Plex Mono',monospace;background:#0f1320;color:#a78bfa;padding:1px 5px;border-radius:3px;font-size:11px;border:1px solid var(--border2)}
.rec-cell pre{background:#080b13;border:1px solid var(--border2);border-radius:6px;padding:10px 14px;margin:7px 0;overflow-x:auto;font-size:11px;line-height:1.5;color:#a8b4d0}
.rec-cell pre code{background:none;color:inherit;padding:0;border:none;font-size:11px}
.fp-note{background:var(--fp-bg);border:1px solid rgba(192,132,252,.25);border-radius:6px;padding:8px 12px;margin-top:6px;font-size:11px;color:var(--fp)}
.fp-note strong{display:block;margin-bottom:3px;font-size:11px;letter-spacing:.3px}
.score-bar-wrap{display:flex;align-items:center;gap:8px;min-width:140px}
.score-bar-bg{flex:1;height:6px;background:var(--border2);border-radius:3px;overflow:hidden}
.score-bar-fill{height:100%;border-radius:3px}
.score-num{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;min-width:28px;text-align:right}
.flag-chips{display:flex;flex-wrap:wrap;gap:4px}
.flag-chip{font-size:9px;font-weight:700;padding:2px 7px;border-radius:10px;letter-spacing:.3px;background:rgba(245,158,11,.1);color:var(--medium);border:1px solid rgba(245,158,11,.2)}
.flag-chip.sev{background:rgba(255,92,92,.1);color:var(--high);border-color:rgba(255,92,92,.2)}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
footer{text-align:center;padding:28px;color:var(--muted);font-size:11px;border-top:1px solid var(--border);font-family:'IBM Plex Mono',monospace}
@media(max-width:900px){.hdr,.main{padding:20px}.statbar{flex-wrap:wrap}.hdr-top{flex-direction:column}}
</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-top">
    <div class="hdr-title">
      <h1>CodeGuard Pro — Audit Report</h1>
      <p>AI-powered static analysis &middot; Vue 3 &middot; Enterprise Edition</p>
      <span class="target">{target_dir} &mdash; {total_components} components &middot; {total_js_files} JS files</span>
    </div>
    <div class="score-ring-wrap">
      <div class="score-ring">
        <svg width="90" height="90" viewBox="0 0 90 90">
          <circle cx="45" cy="45" r="37" fill="none" stroke="#1e2338" stroke-width="8"/>
          <circle cx="45" cy="45" r="37" fill="none" stroke="{risk_color}" stroke-width="8"
            stroke-dasharray="232.48" stroke-dashoffset="{stroke_offset}" stroke-linecap="round"/>
        </svg>
        <div class="val">{score}<span>/ 100</span></div>
      </div>
      <div class="score-meta">
        <div class="risk" style="color: {risk_color}">{risk_level} RISK</div>
        <p>Overall Health Score</p>
        <p style="margin-top:6px;font-size:11px;color:#8892b0">Generated {date}</p>
      </div>
    </div>
  </div>
</div>

<div class="statbar">
  <div class="stat"><div class="v neutral">{total_components}</div><div class="l">Vue Files</div></div>
  <div class="stat"><div class="v neutral">{total_js_files}</div><div class="l">JS Files</div></div>
  <div class="stat"><div class="v high">{high_issues}</div><div class="l">High Issues</div></div>
  <div class="stat"><div class="v med">{medium_issues}</div><div class="l">Medium Issues</div></div>
  <div class="stat"><div class="v low">{low_issues}</div><div class="l">Low Issues</div></div>
  <div class="stat"><div class="v neutral">{ui_issues}</div><div class="l">UI Issues</div></div>
  <div class="stat"><div class="v neutral">{a11y_issues}</div><div class="l">A11y Issues</div></div>
  <div class="stat"><div class="v neutral">{complex_files}</div><div class="l">Complex Files</div></div>
  <div class="stat"><div class="v fp">{fp_issues}</div><div class="l">False Positives</div></div>
</div>

<div class="main">
<div class="sec">
  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('summary',this)">Summary</button>
    <button class="tab-btn" onclick="switchTab('ui',this)">UI Consistency ({ui_issues})</button>
    <button class="tab-btn" onclick="switchTab('a11y',this)">Accessibility ({a11y_issues})</button>
    <button class="tab-btn" onclick="switchTab('complexity',this)">Complexity ({complex_files})</button>
    <button class="tab-btn" onclick="switchTab('filescores',this)">File Scores</button>
  </div>

  <!-- SUMMARY -->
  <div id="tab-summary" class="tab-pane active">
    <div class="summary-grid">
      <div class="sum-card">
        <h3><span></span> Summary & Insights</h3>
        <p style="font-size:13px; color:var(--muted); line-height: 1.6;">
          This report incorporates automated recommendations for User Interface consistency and Web Accessibility (WCAG). Components with structural complexity issues are listed under the Complexity tab. Consult File Scores to prioritize technical debt.
        </p>
      </div>
    </div>
  </div>

  <!-- UI CONSISTENCY -->
  <div id="tab-ui" class="tab-pane">
  <div class="sec-body"><table>
    <thead><tr><th>#</th><th>File</th><th>Rule</th><th>Finding</th><th>Severity</th><th>Recommendation</th></tr></thead>
    <tbody>
      {ui_rows}
    </tbody>
  </table></div>
  </div>

  <!-- ACCESSIBILITY -->
  <div id="tab-a11y" class="tab-pane">
  <div class="sec-body"><table>
    <thead><tr><th>#</th><th>File</th><th>Rule</th><th>Finding</th><th>Sev</th><th>Recommendation</th></tr></thead>
    <tbody>
      {a11y_rows}
    </tbody>
  </table></div>
  </div>

  <!-- COMPLEXITY -->
  <div id="tab-complexity" class="tab-pane">
  <div class="sec-body"><table>
    <thead><tr><th>Component</th><th>LOC</th><th>Methods</th><th>Watchers</th><th>Template Lines</th><th>Flags</th><th>Relative Complexity Factor</th></tr></thead>
    <tbody>
      {cx_rows}
    </tbody>
  </table></div>
  </div>

  <!-- FILE SCORES -->
  <div id="tab-filescores" class="tab-pane">
  <div class="sec-body"><table>
    <thead><tr><th>File</th><th>Path</th><th>API Count</th><th>LOC</th><th>Flags</th></tr></thead>
    <tbody>
      {ff_rows}
    </tbody>
  </table></div>
  </div>

</div><!-- .sec -->
</div><!-- .main -->

<footer>
  CodeGuard Pro &nbsp;&middot;&nbsp; AI-Powered Analysis Engine &nbsp;&middot;&nbsp; Generated {date}
</footer>

<script>
function switchTab(id, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  btn.classList.add('active');
}
</script>
</body>
</html>
"""
