import os
import json
import html

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

def load_json(filename):
    path = os.path.join(REPORTS_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def main():
    ui_issues = load_json("ui_consistency_report.json")
    acc_issues = load_json("accessibility_report.json")

    # Combine issues
    all_issues = ui_issues + acc_issues
    
    # Filter only FAIL and having a valid file
    issues = [i for i in all_issues if i.get("status", "").upper() == "FAIL" and i.get("file_path") and not str(i.get("file_path")).endswith(".json")]

    # Group by file path
    grouped = {}
    for i in issues:
        path = i.get("file_path")
        if path not in grouped:
            grouped[path] = []
        grouped[path].append(i)

    # HTML template start
    html_content = ["""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Code Error Viewer</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; display: flex; height: 100vh; background-color: #f4f4f9; color: #333; }
            .sidebar { width: 350px; background-color: #fff; border-right: 1px solid #ddd; overflow-y: auto; padding: 10px; box-shadow: 2px 0 5px rgba(0,0,0,0.05); }
            .sidebar h2 { font-size: 16px; border-bottom: 2px solid #3b5fe2; padding-bottom: 5px; color: #3b5fe2; margin-top: 5px; }
            .file-list { list-style: none; padding: 0; margin: 0; }
            .file-list li { margin-bottom: 5px; }
            .file-list button { width: 100%; text-align: left; padding: 10px; border: 1px solid #eee; background: none; border-radius: 4px; cursor: pointer; font-size: 13px; transition: 0.2s; word-break: break-all;}
            .file-list button:hover { background-color: #f0f4ff; border-color: #3b5fe2; }
            .file-list button.active { background-color: #e6edff; border-color: #3b5fe2; font-weight: bold; }
            
            .main-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
            .header { padding: 15px 20px; background-color: #fff; border-bottom: 1px solid #ddd; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.02); z-index: 10;}
            .header h2 { margin: 0; font-size: 18px; font-weight: 600; color: #333; word-break: break-all;}
            
            .code-container { flex: 1; overflow: auto; padding: 20px 0; background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas, 'Courier New', monospace; font-size: 14px; line-height: 1.5; }
            
            .code-line { display: flex; white-space: pre; margin: 0; padding: 0; width: fit-content; min-width: 100%;}
            .line-number { min-width: 40px; padding-right: 15px; text-align: right; color: #858585; user-select: none; border-right: 1px solid #404040; margin-right: 15px; background: #1e1e1e;}
            .line-content { flex: 1; padding-right: 20px; }
            
            .highlight-high { background-color: rgba(220, 38, 38, 0.2); }
            .highlight-high .line-number { border-left: 3px solid #dc2626; color: #f87171;}
            .highlight-medium { background-color: rgba(217, 119, 6, 0.2); }
            .highlight-medium .line-number { border-left: 3px solid #d97706; color: #fbbf24;}
            .highlight-low { background-color: rgba(2, 132, 199, 0.2); }
            .highlight-low .line-number { border-left: 3px solid #0284c7; color: #38bdf8;}
            
            .error-box-container { margin: 0 20px 15px 65px; }
            .error-box { background-color: #fff; border-left: 4px solid #dc2626; padding: 10px 15px; margin-top: 5px; border-radius: 0 4px 4px 0; margin-bottom: 10px; font-family: 'Segoe UI', sans-serif; color: #333; white-space: normal; line-height: 1.4; box-shadow: 0 2px 4px rgba(0,0,0,0.1); font-size:13px; max-width: 800px;}
            .error-box strong { color: #dc2626; display:inline-block; margin-bottom: 5px; font-size:12px; text-transform:uppercase; letter-spacing:0.5px;}
            .error-box .medium { color: #d97706; border-color: #d97706; }
            .error-box .low { color: #0284c7; border-color: #0284c7; }
            
            .stats { display: flex; gap: 10px; font-size: 12px; margin-top: 5px; font-weight: normal; color: #666; }
            .badge { padding: 3px 8px; border-radius: 12px; font-weight: 600; color: white; }
            .bg-high { background-color: #dc2626; }
            .bg-medium { background-color: #d97706; }
            .bg-low { background-color: #0284c7; }
            
            .file-panel { display: none; height: 100%; flex-direction: column; }
            .file-panel.active { display: flex; }
            
            .instruction { display:flex; justify-content:center; align-items:center; height:100%; flex-direction:column; color:#888; background: #fff;}
            .instruction h2 { font-weight: 400;}
        </style>
    </head>
    <body>
        <div class="sidebar">
            <h2>Analyzed Files with Errors</h2>
            <ul class="file-list">
    """]
    
    # Store file contents to generate later to avoid massive memory
    panels_html = []
    
    file_id = 0
    # Sort files so that the ones with HIGH issues come first
    def get_max_sev(f_issues):
        sevs = [i.get('severity', 'LOW').upper() for i in f_issues]
        if 'HIGH' in sevs: return 3
        if 'MEDIUM' in sevs: return 2
        if 'LOW' in sevs: return 1
        return 0

    sorted_grouped = sorted(grouped.items(), key=lambda x: (-get_max_sev(x[1]), len(x[1]), x[0]))

    for file_path, file_issues in sorted_grouped:
        file_id += 1
        basename = os.path.basename(file_path)
        
        # Calculate stats
        high = len([i for i in file_issues if i.get("severity", "LOW").upper() == "HIGH"])
        med = len([i for i in file_issues if i.get("severity", "LOW").upper() == "MEDIUM"])
        low = len([i for i in file_issues if i.get("severity", "LOW").upper() == "LOW"])
        
        badge_html = ""
        if high: badge_html += f'<span class="badge bg-high">{high}</span>'
        if med: badge_html += f'<span class="badge bg-medium">{med}</span>'
        if low: badge_html += f'<span class="badge bg-low">{low}</span>'
        
        html_content.append(f"""
            <li>
                <button onclick="showFile('file-{file_id}', this)">
                    <strong>{html.escape(basename)}</strong><br>
                    <div style="font-size:10px; color:#666; margin-top:4px;">{html.escape(file_path)}</div>
                    <div class="stats" style="margin-top: 6px;">{badge_html}</div>
                </button>
            </li>
        """)
        
        # Read file logic
        file_content = []
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    file_content = f.readlines()
            except Exception as e:
                file_content = [f"Error reading file: {e}\n"]
        else:
            file_content = [f"File not found on system: {file_path}\n"]
            
        # Parse lines per issue
        line_errors = {}
        for issue in file_issues:
            ln_str = str(issue.get("line_number", ""))
            sev = issue.get("severity", "LOW").upper()
            rule = issue.get("rule_name", "Unknown Rule")
            msg = issue.get("actual_result", "")
            
            start_ln = end_ln = -1
            if ln_str and ln_str not in ["0-0", "0", "None-None", "None"]:
                if "-" in ln_str:
                    parts = ln_str.split("-")
                    try:
                        start_ln = int(parts[0])
                        end_ln = int(parts[1])
                    except: pass
                else:
                    try:
                        start_ln = int(ln_str)
                        end_ln = int(ln_str)
                    except: pass
            
            if start_ln > 0:
                for ln in range(start_ln, end_ln + 1):
                    if ln not in line_errors:
                        line_errors[ln] = []
                    # Check for duplicates on same line
                    is_dup = False
                    for existing in line_errors[ln]:
                        if existing['rule'] == rule and existing['msg'] == msg:
                            is_dup = True
                            break
                    if not is_dup:
                        line_errors[ln].append({"sev": sev, "rule": rule, "msg": msg})
            else:
                if 0 not in line_errors:
                    line_errors[0] = []
                line_errors[0].append({"sev": sev, "rule": rule, "msg": msg})
        
        # Generate Panel HTML
        panels_html.append(f"""
        <div id="file-{file_id}" class="file-panel">
            <div class="header">
                <div>
                    <h2>{html.escape(basename)}</h2>
                    <div style="font-size: 13px; color: #666; margin-top: 5px;">{html.escape(file_path)}</div>
                </div>
            </div>
            <div class="code-container" id="code-container-{file_id}">
        """)
        
        if 0 in line_errors:
            panels_html.append('<div class="error-box-container">')
            for err in line_errors[0]:
                sev_cls = err['sev'].lower()
                panels_html.append(f"""
                    <div class="error-box" style="border-left-color: {'#dc2626' if sev_cls=='high' else '#d97706' if sev_cls=='medium' else '#0284c7'};">
                        <strong style="color: {'#dc2626' if sev_cls=='high' else '#d97706' if sev_cls=='medium' else '#0284c7'};">[GLOBAL {err['sev']}] {html.escape(err['rule'])}</strong><br>
                        {html.escape(err['msg'])}
                    </div>
                """)
            panels_html.append('</div>')
            
        for idx, line_text in enumerate(file_content):
            ln = idx + 1
            line_html_escaped = html.escape(line_text.rstrip('\r\n'))
            if not line_html_escaped: line_html_escaped = " "
            
            if ln in line_errors:
                # Get max severity
                sevs = [e["sev"] for e in line_errors[ln]]
                max_sev = "LOW"
                if "HIGH" in sevs: max_sev = "HIGH"
                elif "MEDIUM" in sevs: max_sev = "MEDIUM"
                
                hl_class = f"highlight-{max_sev.lower()}"
                
                panels_html.append(f'<div class="code-line {hl_class}" id="line-{file_id}-{ln}"><div class="line-number">{ln}</div><div class="line-content">{line_html_escaped}</div></div>')
                
                # Check for errors to display below this line (only if first line of the block)
                errors_to_show_now = []
                for err in line_errors[ln]:
                    if ln == 1 or ln - 1 not in line_errors or err not in line_errors[ln-1]:
                        errors_to_show_now.append(err)
                
                if errors_to_show_now:
                    panels_html.append('<div class="code-line" style="background:#1e1e1e;"><div class="line-number" style="border-right:1px solid #404040;"></div><div class="line-content" style="padding:5px 0;">')
                    for err in errors_to_show_now:
                        sev_cls = err['sev'].lower()
                        panels_html.append(f"""
                            <div class="error-box" style="border-left-color: {'#dc2626' if sev_cls=='high' else '#d97706' if sev_cls=='medium' else '#0284c7'}; margin-left: 20px;">
                                <strong style="color: {'#dc2626' if sev_cls=='high' else '#d97706' if sev_cls=='medium' else '#0284c7'};">[{err['sev']}] {html.escape(err['rule'])}</strong><br>
                                {html.escape(err['msg'])}
                            </div>
                        """)
                    panels_html.append('</div></div>')
                    
            else:
                panels_html.append(f'<div class="code-line"><div class="line-number">{ln}</div><div class="line-content">{line_html_escaped}</div></div>')
                
        panels_html.append("""
            </div>
        </div>
        """)
        
    html_content.append("""
            </ul>
        </div>
        <div class="main-content" id="main-area">
            <div class="instruction" id="instruction-panel">
                <svg width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="#ccc" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom:20px;">
                    <polyline points="16 18 22 12 16 6"></polyline>
                    <polyline points="8 6 2 12 8 18"></polyline>
                </svg>
                <h2>Select a file from the sidebar to view highlighted errors</h2>
            </div>
    """)
    
    for p in panels_html:
        html_content.append(p)
        
    html_content.append("""
        </div>
        <script>
            function showFile(id, btn) {
                // Hide ALL children of main-area
                var children = document.getElementById('main-area').children;
                for (var i = 0; i < children.length; i++) {
                    children[i].style.display = 'none';
                }
                
                // Show requested file
                var filePanel = document.getElementById(id);
                if (filePanel) {
                    filePanel.style.display = 'flex';
                }
                
                // Active class on button
                var btns = document.querySelectorAll('.file-list button');
                for (var i = 0; i < btns.length; i++) {
                    btns[i].classList.remove('active');
                }
                if (btn) btn.classList.add('active');
                
                // Scroll to the first highlighted error line if exists
                setTimeout(() => {
                    var containerId = 'code-container-' + id.replace('file-', '');
                    var container = document.getElementById(containerId);
                    if (container) {
                        var firstHighlight = container.querySelector('[class*="highlight-"]');
                        if (firstHighlight) {
                            var topPos = firstHighlight.offsetTop;
                            // subtract a bit of margin so it's not glued to the top
                            container.scrollTop = Math.max(0, topPos - 100);
                        }
                    }
                }, 50);
            }
        </script>
    </body>
    </html>
    """)
    
    with open("reports/code_viewer_report.html", "w", encoding="utf-8") as f:
        f.write("".join(html_content))
    print("Report generated successfully at reports/code_viewer_report.html")

if __name__ == "__main__":
    main()
