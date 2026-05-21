"""
Report Generator - Creates a standalone HTML report from scan results.
"""

import sys
import os
import json
import html

# Add parent to path
sys.path.insert(0, os.path.dirname(__file__))

from scanner_engine import ScannerEngine


def generate_html_report(scan_result: dict) -> str:
    issues = scan_result.get('issues', [])
    summary = scan_result.get('summary', {})
    
    # Group issues by file
    by_file = {}
    for issue in issues:
        fname = issue['file']
        short = os.path.basename(fname)
        if short not in by_file:
            by_file[short] = {'path': fname, 'issues': []}
        by_file[short]['issues'].append(issue)

    # Build issue rows HTML
    file_sections = ''
    for short_name, data in by_file.items():
        high = sum(1 for i in data['issues'] if i['severity'] == 'high')
        med = sum(1 for i in data['issues'] if i['severity'] == 'medium')
        low = sum(1 for i in data['issues'] if i['severity'] == 'low')
        
        issue_rows = ''
        for issue in data['issues']:
            sev = issue['severity']
            sev_class = {'high': 'badge-high', 'medium': 'badge-medium', 'low': 'badge-low'}[sev]
            cat_label = html.escape(issue.get('category', ''))
            msg = html.escape(issue.get('message', ''))
            desc = html.escape(issue.get('description', ''))
            rule = html.escape(issue.get('rule_id', ''))
            line = issue.get('line', 0)
            
            fix_html = ''
            if issue.get('fix'):
                fix = issue['fix']
                orig = html.escape(fix.get('original', ''))
                repl = html.escape(fix.get('replacement', ''))
                fix_desc = html.escape(fix.get('description', ''))
                fix_html = f'''
                <div class="fix-block">
                    <div class="fix-title">Suggested Fix: {fix_desc}</div>
                    <div class="diff-line removed">- {orig}</div>
                    <div class="diff-line added">+ {repl}</div>
                </div>'''
            
            issue_rows += f'''
            <div class="issue-card">
                <div class="issue-header-row">
                    <span class="badge {sev_class}">{sev.upper()}</span>
                    <span class="badge badge-cat">{cat_label}</span>
                    <span class="issue-msg">{msg}</span>
                    <span class="line-num">Line {line}</span>
                </div>
                <div class="issue-desc">{desc}</div>
                <div class="issue-rule">Rule: <code>{rule}</code></div>
                {fix_html}
            </div>'''
        
        file_sections += f'''
        <div class="file-section">
            <div class="file-header" onclick="this.parentElement.classList.toggle('collapsed')">
                <div class="file-name">
                    <span class="chevron">&#x25BC;</span>
                    <strong>{html.escape(short_name)}</strong>
                </div>
                <div class="file-badges">
                    {'<span class="badge badge-high">' + str(high) + ' High</span>' if high else ''}
                    {'<span class="badge badge-medium">' + str(med) + ' Medium</span>' if med else ''}
                    {'<span class="badge badge-low">' + str(low) + ' Low</span>' if low else ''}
                </div>
            </div>
            <div class="file-body">
                {issue_rows}
            </div>
        </div>'''

    total = summary.get('total', len(issues))
    high_total = summary.get('high', 0)
    med_total = summary.get('medium', 0)
    low_total = summary.get('low', 0)
    files_count = scan_result.get('file_count', 0)
    duration = scan_result.get('scan_duration', 0)
    
    # Category breakdown
    by_cat = summary.get('by_category', {})
    cat_bars = ''
    max_cat = max(by_cat.values()) if by_cat else 1
    for cat, count in sorted(by_cat.items(), key=lambda x: -x[1]):
        pct = (count / max_cat) * 100
        cat_bars += f'''
        <div class="cat-row">
            <span class="cat-label">{html.escape(cat.title())}</span>
            <div class="cat-bar-bg">
                <div class="cat-bar-fill" style="width: {pct}%"></div>
            </div>
            <span class="cat-count">{count}</span>
        </div>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vue UI/UX Analyzer - Scan Report</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  
  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #0f0f1a;
    color: #e0e0e8;
    min-height: 100vh;
  }}
  
  .header {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 40px 0 60px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    position: relative;
    overflow: hidden;
  }}
  
  .header::before {{
    content: '';
    position: absolute;
    top: -80px; right: -80px;
    width: 300px; height: 300px;
    background: radial-gradient(circle, rgba(66,184,131,0.15) 0%, transparent 70%);
    border-radius: 50%;
  }}
  
  .header::after {{
    content: '';
    position: absolute;
    bottom: -60px; left: 20%;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(84,160,255,0.1) 0%, transparent 70%);
    border-radius: 50%;
  }}
  
  .container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 24px;
    position: relative;
    z-index: 1;
  }}
  
  .brand {{
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 32px;
  }}
  
  .brand svg {{ width: 44px; height: 44px; }}
  
  .brand-text h1 {{
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.5px;
    background: linear-gradient(135deg, #42b883, #64d8a4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }}
  
  .brand-text p {{
    font-size: 14px;
    opacity: 0.5;
    margin-top: 2px;
  }}
  
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
  }}
  
  .stat-card {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 20px;
    text-align: center;
    backdrop-filter: blur(10px);
    transition: transform 0.2s, box-shadow 0.2s;
  }}
  
  .stat-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  }}
  
  .stat-num {{
    font-size: 36px;
    font-weight: 800;
    line-height: 1.1;
  }}
  
  .stat-num.total {{ color: #feca57; }}
  .stat-num.high {{ color: #ff6b6b; }}
  .stat-num.medium {{ color: #ffa94d; }}
  .stat-num.low {{ color: #54a0ff; }}
  .stat-num.files {{ color: #42b883; }}
  
  .stat-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.5;
    margin-top: 8px;
    font-weight: 600;
  }}
  
  .body-content {{
    padding: 40px 0 80px;
  }}
  
  .section-title {{
    font-size: 20px;
    font-weight: 700;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  
  .section-title::before {{
    content: '';
    display: block;
    width: 4px;
    height: 24px;
    background: linear-gradient(180deg, #42b883, #54a0ff);
    border-radius: 2px;
  }}
  
  /* Category breakdown */
  .cat-breakdown {{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 40px;
  }}
  
  .cat-row {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
  }}
  
  .cat-label {{
    width: 120px;
    font-size: 13px;
    font-weight: 500;
    text-align: right;
  }}
  
  .cat-bar-bg {{
    flex: 1;
    height: 8px;
    background: rgba(255,255,255,0.06);
    border-radius: 4px;
    overflow: hidden;
  }}
  
  .cat-bar-fill {{
    height: 100%;
    background: linear-gradient(90deg, #42b883, #54a0ff);
    border-radius: 4px;
    transition: width 1s ease;
  }}
  
  .cat-count {{
    width: 40px;
    font-size: 14px;
    font-weight: 700;
    color: #42b883;
  }}
  
  /* File sections */
  .file-section {{
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    margin-bottom: 16px;
    overflow: hidden;
    transition: box-shadow 0.2s;
  }}
  
  .file-section:hover {{
    box-shadow: 0 4px 16px rgba(0,0,0,0.2);
  }}
  
  .file-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    cursor: pointer;
    background: rgba(255,255,255,0.03);
    border-bottom: 1px solid rgba(255,255,255,0.04);
    transition: background 0.2s;
  }}
  
  .file-header:hover {{
    background: rgba(255,255,255,0.06);
  }}
  
  .file-name {{
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
  }}
  
  .chevron {{
    transition: transform 0.3s;
    font-size: 12px;
    opacity: 0.5;
  }}
  
  .collapsed .chevron {{ transform: rotate(-90deg); }}
  .collapsed .file-body {{ display: none; }}
  
  .file-badges {{ display: flex; gap: 8px; }}
  
  .badge {{
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
  }}
  
  .badge-high {{ background: rgba(255,107,107,0.15); color: #ff6b6b; }}
  .badge-medium {{ background: rgba(255,169,77,0.15); color: #ffa94d; }}
  .badge-low {{ background: rgba(84,160,255,0.15); color: #54a0ff; }}
  .badge-cat {{ background: rgba(255,255,255,0.06); color: #aaa; }}
  
  .issue-card {{
    padding: 20px 24px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    transition: background 0.2s;
  }}
  
  .issue-card:hover {{
    background: rgba(255,255,255,0.02);
  }}
  
  .issue-card:last-child {{ border-bottom: none; }}
  
  .issue-header-row {{
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }}
  
  .issue-msg {{
    font-weight: 600;
    font-size: 14px;
    flex: 1;
    min-width: 200px;
  }}
  
  .line-num {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    opacity: 0.4;
    padding: 2px 8px;
    background: rgba(255,255,255,0.04);
    border-radius: 4px;
  }}
  
  .issue-desc {{
    font-size: 13px;
    opacity: 0.6;
    margin-top: 8px;
    line-height: 1.6;
    padding-left: 4px;
  }}
  
  .issue-rule {{
    font-size: 11px;
    opacity: 0.35;
    margin-top: 6px;
    padding-left: 4px;
  }}
  
  .issue-rule code {{
    background: rgba(255,255,255,0.06);
    padding: 1px 6px;
    border-radius: 3px;
    font-family: 'JetBrains Mono', monospace;
  }}
  
  .fix-block {{
    margin-top: 12px;
    background: rgba(0,0,0,0.3);
    border-radius: 8px;
    padding: 14px 16px;
    border-left: 3px solid #42b883;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
    overflow-x: auto;
  }}
  
  .fix-title {{
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    opacity: 0.5;
    margin-bottom: 8px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  
  .diff-line {{
    padding: 3px 6px;
    border-radius: 3px;
    margin-bottom: 2px;
    white-space: pre-wrap;
    word-break: break-all;
  }}
  
  .diff-line.removed {{
    background: rgba(255,107,107,0.1);
    color: #ff8a8a;
  }}
  
  .diff-line.added {{
    background: rgba(66,184,131,0.1);
    color: #6ee7a8;
  }}
  
  .footer-bar {{
    text-align: center;
    padding: 32px;
    font-size: 12px;
    opacity: 0.3;
    border-top: 1px solid rgba(255,255,255,0.04);
  }}
</style>
</head>
<body>

<div class="header">
  <div class="container">
    <div class="brand">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
        <defs>
          <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:#42b883"/>
            <stop offset="100%" style="stop-color:#35495e"/>
          </linearGradient>
        </defs>
        <path fill="url(#g)" d="M12 2L2 19h4l6-10.5L18 19h4L12 2z"/>
      </svg>
      <div class="brand-text">
        <h1>Vue UI/UX Analyzer</h1>
        <p>Scan Report &mdash; {files_count} file(s) analyzed in {duration}s</p>
      </div>
    </div>
    
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-num total">{total}</div>
        <div class="stat-label">Total Issues</div>
      </div>
      <div class="stat-card">
        <div class="stat-num high">{high_total}</div>
        <div class="stat-label">High Severity</div>
      </div>
      <div class="stat-card">
        <div class="stat-num medium">{med_total}</div>
        <div class="stat-label">Medium Severity</div>
      </div>
      <div class="stat-card">
        <div class="stat-num low">{low_total}</div>
        <div class="stat-label">Low Severity</div>
      </div>
      <div class="stat-card">
        <div class="stat-num files">{files_count}</div>
        <div class="stat-label">Files Scanned</div>
      </div>
    </div>
  </div>
</div>

<div class="body-content">
  <div class="container">
    <div class="section-title">Issues by Category</div>
    <div class="cat-breakdown">
      {cat_bars}
    </div>
    
    <div class="section-title">Detected Issues</div>
    {file_sections}
  </div>
</div>

<div class="footer-bar">
  Vue UI/UX Analyzer &bull; Powered by Python + Vue.js
</div>

</body>
</html>'''


if __name__ == '__main__':
    project_path = sys.argv[1] if len(sys.argv) > 1 else '.'
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'report.html'
    
    scanner = ScannerEngine()
    result = scanner.scan_project(project_path, force=True)
    
    report_html = generate_html_report(result)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report_html)
    
    print(f"Report generated: {os.path.abspath(output_file)}")
    print(f"Total issues: {result['summary']['total']}")
    print(f"  High: {result['summary']['high']}, Medium: {result['summary']['medium']}, Low: {result['summary']['low']}")
