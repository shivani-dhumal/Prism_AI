"""Generate static HTML report: tree hierarchy + fix diff modal."""
import json, os, decimal
from datetime import datetime
from database_ops import get_db

conn = get_db()
cur = conn.cursor(dictionary=True)

cur.execute("""
    SELECT id, file_name, file_path, bug_category, title, severity,
           line_number, description, fix_suggestion, confidence, status
    FROM bug_detections
    ORDER BY FIELD(severity,'CRITICAL','HIGH','MEDIUM','LOW'), file_name, line_number
""")
bugs = cur.fetchall()

cur.execute("""SELECT COUNT(*) as total,
  SUM(severity='CRITICAL') as critical, SUM(severity='HIGH') as high,
  SUM(severity='MEDIUM') as medium, SUM(severity='LOW') as low,
  SUM(status='OPEN') as open_cnt, SUM(status='FIXED') as fixed_cnt,
  SUM(status='IGNORED') as ignored_cnt FROM bug_detections""")
stats = cur.fetchone()
cur.close(); conn.close()

def fix(v):
    return int(v) if isinstance(v, decimal.Decimal) else (0 if v is None else v)

for row in list(bugs) + [stats]:
    for k in row:
        row[k] = fix(row[k])

now   = datetime.now().strftime("%B %d, %Y at %I:%M %p")
total = stats['total']
crit  = stats['critical']
high  = stats['high']
med   = stats['medium']
low   = stats['low']
health = max(0, min(100, round(100 - (crit*15 + high*6 + med*2 + low*0.5))))
health_color = '#16A34A' if health >= 70 else '#D97706' if health >= 40 else '#DC2626'

SEV_C  = {'CRITICAL':'#DC2626','HIGH':'#EA580C','MEDIUM':'#D97706','LOW':'#2563EB'}
SEV_BG = {'CRITICAL':'#FEF2F2','HIGH':'#FFF7ED','MEDIUM':'#FFFBEB','LOW':'#EFF6FF'}
SEV_BD = {'CRITICAL':'#FECACA','HIGH':'#FED7AA','MEDIUM':'#FDE68A','LOW':'#BFDBFE'}

CAT_LBL = {
    'logic_error':'Logic Error','null_deref':'Null Dereference',
    'api_misuse':'API Misuse','error_handling':'Error Handling',
    'security':'Security','dead_code':'Dead Code',
    'type_error':'Type Error','data_flow':'Data Flow',
    'resource_leak':'Resource Leak','concurrency':'Concurrency',
}
CAT_ICO = {
    'security':'🔐','logic_error':'🧠','null_deref':'💥',
    'api_misuse':'⚠️','error_handling':'🚨','dead_code':'🪦',
    'type_error':'🔢','data_flow':'🌊','resource_leak':'🚰','concurrency':'⚡',
}

def file_icon(name):
    e = name.rsplit('.',1)[-1].lower() if '.' in name else ''
    icons = {'vue':'vue','js':'js','ts':'ts','jsx':'jsx','tsx':'tsx',
             'html':'html','css':'css','scss':'scss','py':'py','json':'json'}
    return icons.get(e,'file')

def esc(s):
    return str(s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def read_code_snippet(file_path, line_number, context=6):
    """Read lines around the bug line from the actual file."""
    try:
        if not file_path or not os.path.exists(file_path):
            return None, None
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
        total_lines = len(all_lines)
        ln = max(1, int(line_number)) if line_number else 1
        start = max(0, ln - context - 1)
        end   = min(total_lines, ln + context)
        snippet = []
        for i in range(start, end):
            snippet.append({'num': i+1, 'code': all_lines[i].rstrip('\n\r'), 'highlight': (i+1)==ln})
        return snippet, ln
    except Exception:
        return None, None

# ── Build folder tree ──────────────────────────────────────────────────────────
# group bugs by file
from collections import defaultdict
bugs_by_file = defaultdict(list)
for b in bugs:
    key = (b['file_name'], b['file_path'])
    bugs_by_file[key].append(b)

# normalise paths → build nested dict tree
tree = {}  # nested dict; leaf = {'__bugs__': [...], '__path__': fp}

def add_to_tree(parts, fp, bug_list, node):
    if not parts:
        return
    part = parts[0]
    if len(parts) == 1:  # file node
        node[part] = {'__file__': True, '__path__': fp, '__bugs__': bug_list}
    else:
        if part not in node:
            node[part] = {}
        add_to_tree(parts[1:], fp, bug_list, node[part])

for (fn, fp), bug_list in bugs_by_file.items():
    if fp:
        # use last 5 path parts so tree isn't too deep
        parts = fp.replace('\\','/').split('/')
        # find a reasonable root (trim absolute prefix, keep last 6 segments)
        parts = [p for p in parts if p]
        if len(parts) > 6:
            parts = parts[-6:]
    else:
        parts = [fn]
    add_to_tree(parts, fp, bug_list, tree)

def count_tree_bugs(node):
    if node.get('__file__'):
        return len(node['__bugs__'])
    total = 0
    for k,v in node.items():
        if isinstance(v, dict):
            total += count_tree_bugs(v)
    return total

def worst_sev(bug_list):
    for s in ['CRITICAL','HIGH','MEDIUM','LOW']:
        if any(b['severity']==s for b in bug_list):
            return s
    return 'LOW'

# Pre-fetch code snippets and build issue data JSON
all_issues_data = []
issue_counter = [0]

def build_tree_html(node, depth=0, path_prefix=''):
    html = ''
    indent = depth * 18
    # sort: folders first, then files
    dirs  = [(k,v) for k,v in node.items() if isinstance(v,dict) and not v.get('__file__')]
    files = [(k,v) for k,v in node.items() if isinstance(v,dict) and v.get('__file__')]
    dirs.sort(key=lambda x: x[0].lower())
    files.sort(key=lambda x: (
        -['CRITICAL','HIGH','MEDIUM','LOW'].index(worst_sev(x[1]['__bugs__'])) if x[1]['__bugs__'] else 999,
        x[0].lower()
    ))

    for folder_name, subtree in dirs:
        bc = count_tree_bugs(subtree)
        folder_id = f"folder_{abs(hash(path_prefix+folder_name))}"
        worst = None
        # collect all bugs in subtree
        def collect(n):
            r=[]
            for kk,vv in n.items():
                if isinstance(vv,dict):
                    if vv.get('__file__'):
                        r.extend(vv['__bugs__'])
                    else:
                        r.extend(collect(vv))
            return r
        all_in_folder = collect(subtree)
        w = worst_sev(all_in_folder) if all_in_folder else None
        wc = SEV_C.get(w,'#6B7280') if w else '#6B7280'
        cnt_badge = f'<span class="tree-cnt" style="background:{SEV_BG.get(w,"#F9FAFB")};color:{wc};border-color:{SEV_BD.get(w,"#E5E7EB")}">{bc}</span>' if bc else ''
        html += f'''
        <div class="tree-row tree-folder" style="padding-left:{indent+4}px" onclick="toggleNode('{folder_id}')">
          <span class="tree-arrow" id="arr-{folder_id}">▶</span>
          <span class="tree-icon folder-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M3 7a2 2 0 012-2h4.586a1 1 0 01.707.293L12 7h7a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" fill="#F59E0B" stroke="#D97706" stroke-width="1.5"/></svg>
          </span>
          <span class="tree-name">{esc(folder_name)}</span>
          {cnt_badge}
        </div>
        <div class="tree-children" id="{folder_id}" style="display:none">
          {build_tree_html(subtree, depth+1, path_prefix+folder_name+'/')}
        </div>'''

    for file_name, fnode in files:
        fp = fnode['__path__']
        fbug_list = fnode['__bugs__']
        ft = len(fbug_list)
        file_id = f"file_{abs(hash(fp or file_name))}"
        w = worst_sev(fbug_list) if fbug_list else None
        wc = SEV_C.get(w,'#6B7280') if w else '#6B7280'
        ext = file_icon(file_name)

        cnt_badge = f'<span class="tree-cnt err" style="background:{SEV_BG.get(w,"#F9FAFB")};color:{wc};border-color:{SEV_BD.get(w,"#E5E7EB")}">{ft} issue{"s" if ft!=1 else ""}</span>' if ft else ''

        issues_html = ''
        for b in fbug_list:
            issue_counter[0] += 1
            iid = f"issue_{issue_counter[0]}"
            sev = b.get('severity','MEDIUM')
            sc  = SEV_C.get(sev,'#6B7280')
            sbg = SEV_BG.get(sev,'#F9FAFB')
            sbd = SEV_BD.get(sev,'#E5E7EB')
            cat = b.get('bug_category','')
            cat_lbl = CAT_LBL.get(cat, cat.replace('_',' ').title())
            cat_ico = CAT_ICO.get(cat,'🔍')
            ln   = b.get('line_number',0)
            conf = round(float(b.get('confidence',0.5))*100)
            title= esc(b.get('title',''))
            desc = esc(b.get('description',''))
            fix_s= b.get('fix_suggestion','') or ''

            # Read code snippet from file
            snippet, actual_line = read_code_snippet(fp, ln)

            # Store issue data for JS
            issue_data = {
                'id': iid,
                'title': b.get('title',''),
                'severity': sev,
                'category': cat_lbl,
                'cat_icon': cat_ico,
                'line': ln,
                'confidence': conf,
                'description': b.get('description',''),
                'fix_suggestion': fix_s,
                'file_name': file_name,
                'file_path': fp or '',
                'snippet': snippet or [],
                'sev_color': sc,
                'sev_bg': sbg,
                'sev_bd': sbd,
            }
            all_issues_data.append(issue_data)

            fix_btn = f'<button class="fix-btn" onclick="showFix(\'{iid}\');event.stopPropagation()"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg> View Fix</button>'

            issues_html += f'''
            <div class="issue-item" id="{iid}">
              <div class="issue-sev-stripe" style="background:{sc}"></div>
              <div class="issue-content">
                <div class="issue-header">
                  <span class="sev-dot" style="background:{sc}"></span>
                  <span class="issue-title-text">{title}</span>
                  <div class="issue-meta-row">
                    <span class="badge-sev" style="background:{sbg};color:{sc};border-color:{sbd}">{sev}</span>
                    <span class="badge-cat">{cat_ico} {cat_lbl}</span>
                    {f'<span class="badge-ln">L{ln}</span>' if ln else ''}
                    <span class="badge-conf">{conf}%</span>
                    {fix_btn}
                  </div>
                </div>
                <p class="issue-desc">{desc}</p>
              </div>
            </div>'''

        html += f'''
        <div class="tree-row tree-file" style="padding-left:{indent+4}px" onclick="toggleNode('{file_id}')">
          <span class="tree-arrow" id="arr-{file_id}">▶</span>
          <span class="tree-icon file-icon ext-{ext}"></span>
          <span class="tree-name file-name-text" style="color:{'#DC2626' if w in ('CRITICAL','HIGH') else '#D97706' if w=='MEDIUM' else '#1E293B'}">{esc(file_name)}</span>
          {cnt_badge}
        </div>
        <div class="tree-children" id="{file_id}" style="display:none">
          <div class="issues-container">
            {issues_html}
          </div>
        </div>'''

    return html

tree_html = build_tree_html(tree)
issues_json = json.dumps(all_issues_data, ensure_ascii=False)

# ── HTML ─────────────────────────────────────────────────────────────────────
css = r"""
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{font-family:'Inter',system-ui,sans-serif;background:#F1F5F9;color:#0F172A;font-size:13px;line-height:1.5;-webkit-font-smoothing:antialiased}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-track{background:#F1F5F9}::-webkit-scrollbar-thumb{background:#CBD5E1;border-radius:6px}

/* ── Topbar ── */
.topbar{background:#fff;border-bottom:1.5px solid #E2E8F0;padding:0 32px;height:56px;display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:200;box-shadow:0 1px 8px rgba(15,23,42,.07)}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none}
.brand-mark{width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,#6366F1,#8B5CF6,#EC4899);display:flex;align-items:center;justify-content:center;box-shadow:0 3px 10px rgba(99,102,241,.4);flex-shrink:0}
.brand-mark svg{width:16px;height:16px}
.brand-name{font-size:15px;font-weight:800;letter-spacing:-.4px;background:linear-gradient(135deg,#6366F1,#8B5CF6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.brand-sub{font-size:9px;font-weight:700;color:#94A3B8;letter-spacing:1px;text-transform:uppercase}
.tb-div{width:1px;height:22px;background:#E2E8F0}
.tb-date{font-size:11px;color:#94A3B8}<br/>.tb-date b{color:#475569}
.tb-spacer{flex:1}
.sev-pill{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:700;border:1.5px solid}
.print-btn{display:flex;align-items:center;gap:6px;padding:6px 14px;border-radius:8px;background:linear-gradient(135deg,#6366F1,#4F46E5);color:#fff;font-size:11.5px;font-weight:600;cursor:pointer;border:none;box-shadow:0 2px 8px rgba(99,102,241,.3);transition:all .15s;flex-shrink:0}
.print-btn:hover{transform:translateY(-1px);box-shadow:0 4px 14px rgba(99,102,241,.45)}

/* ── Layout ── */
.layout{display:flex;min-height:calc(100vh - 56px)}
.sidebar{width:300px;flex-shrink:0;background:#fff;border-right:1.5px solid #E2E8F0;overflow-y:auto;position:sticky;top:56px;height:calc(100vh - 56px)}
.main{flex:1;min-width:0;padding:28px 32px 64px}

/* ── Sidebar header ── */
.sb-hd{padding:14px 16px 10px;border-bottom:1px solid #F1F5F9;display:flex;align-items:center;justify-content:space-between}
.sb-title{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.9px;color:#64748B}
.sb-count{font-size:11px;font-weight:700;color:#6366F1;background:#EEF2FF;padding:2px 8px;border-radius:999px}

/* ── Stats strip ── */
.stats-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border-bottom:1px solid #F1F5F9}
.stat-cell{padding:10px 8px;text-align:center;border-right:1px solid #F1F5F9}
.stat-cell:last-child{border-right:none}
.stat-num{font-size:18px;font-weight:800;font-family:'JetBrains Mono',monospace;line-height:1}
.stat-lbl{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.7px;color:#94A3B8;margin-top:2px}

/* ── Health bar ── */
.health-bar{padding:10px 16px;border-bottom:1px solid #F1F5F9}
.health-row{display:flex;align-items:center;justify-content:space-between;margin-bottom:5px}
.health-lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:#64748B}
.health-val{font-size:13px;font-weight:800;font-family:'JetBrains Mono',monospace}
.health-track{height:6px;background:#F1F5F9;border-radius:999px;overflow:hidden}
.health-fill{height:100%;border-radius:999px;transition:width .6s}

/* ── Tree ── */
.tree-wrap{padding:8px 0 20px}
.tree-row{display:flex;align-items:center;gap:6px;padding:4px 12px;cursor:pointer;user-select:none;transition:background .1s;min-height:28px}
.tree-row:hover{background:#F8FAFC}
.tree-folder{color:#475569}
.tree-file{color:#1E293B}
.tree-arrow{font-size:8px;color:#CBD5E1;transition:transform .15s;flex-shrink:0;width:10px;text-align:center;display:inline-block}
.tree-arrow.open{transform:rotate(90deg)}
.tree-name{font-size:12.5px;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:'JetBrains Mono',monospace}
.folder-name{font-weight:600;color:#475569}
.tree-cnt{font-size:9px;font-weight:700;padding:1px 6px;border-radius:999px;border:1px solid;flex-shrink:0;white-space:nowrap}
.tree-cnt.err{animation:none}
.tree-children{overflow:hidden}

/* File type color dots */
.tree-icon{width:14px;height:14px;border-radius:3px;flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#fff}
.ext-vue{background:#41B883}
.ext-js{background:#F7DF1E;color:#000}
.ext-ts{background:#3178C6}
.ext-jsx,.ext-tsx{background:#61DAFB;color:#000}
.ext-py{background:#3776AB}
.ext-html{background:#E34C26}
.ext-css,.ext-scss{background:#264DE4}
.ext-json{background:#000}
.ext-file{background:#94A3B8}
.ext-vue::after{content:"V"}
.ext-js::after{content:"JS"}
.ext-ts::after{content:"TS"}
.ext-jsx::after{content:"X"}
.ext-tsx::after{content:"X"}
.ext-py::after{content:"PY"}
.ext-html::after{content:"H"}
.ext-css::after,.ext-scss::after{content:"CSS"}
.ext-json::after{content:"{}"}
.ext-file::after{content:"•"}

/* ── Issues container ── */
.issues-container{border-left:2px solid #E2E8F0;margin:0 0 4px 28px}
.issue-item{display:flex;border-bottom:1px solid #F8FAFC;transition:background .1s}
.issue-item:last-child{border-bottom:none}
.issue-item:hover{background:#FAFBFF}
.issue-sev-stripe{width:3px;flex-shrink:0}
.issue-content{flex:1;padding:9px 10px}
.issue-header{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px}
.sev-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.issue-title-text{font-size:12px;font-weight:600;color:#0F172A;flex:1;min-width:120px}
.issue-meta-row{display:flex;align-items:center;gap:4px;flex-wrap:wrap}
.badge-sev{font-size:9px;font-weight:700;padding:1.5px 6px;border-radius:999px;border:1px solid}
.badge-cat{font-size:9.5px;font-weight:500;padding:1.5px 6px;border-radius:4px;background:#F1F5F9;color:#475569;border:1px solid #E2E8F0}
.badge-ln{font-size:9px;font-weight:600;padding:1.5px 5px;border-radius:4px;background:#F0FDF4;color:#16A34A;border:1px solid #BBF7D0;font-family:'JetBrains Mono',monospace}
.badge-conf{font-size:9px;color:#94A3B8;font-family:'JetBrains Mono',monospace}
.issue-desc{font-size:11.5px;color:#64748B;line-height:1.55;margin-top:2px}

/* Fix button */
.fix-btn{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:6px;background:linear-gradient(135deg,#6366F1,#4F46E5);color:#fff;font-size:10px;font-weight:600;cursor:pointer;border:none;box-shadow:0 1px 4px rgba(99,102,241,.35);transition:all .12s;white-space:nowrap}
.fix-btn:hover{box-shadow:0 2px 8px rgba(99,102,241,.5);transform:translateY(-1px)}

/* ── Main content ── */
.page-title{font-size:22px;font-weight:900;color:#0F172A;letter-spacing:-.5px;margin-bottom:3px}
.page-sub{font-size:12.5px;color:#94A3B8;margin-bottom:24px}
.section{background:#fff;border-radius:12px;border:1.5px solid #E2E8F0;margin-bottom:20px;overflow:hidden;box-shadow:0 1px 4px rgba(15,23,42,.05)}
.sec-hd{padding:14px 20px;border-bottom:1.5px solid #F1F5F9;display:flex;align-items:center;gap:8px}
.sec-hd-icon{font-size:16px}
.sec-title{font-size:13px;font-weight:700;color:#0F172A;flex:1}
.sec-sub{font-size:11px;color:#94A3B8}
.sec-body{padding:18px 20px}

/* Cards */
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:0}
.card{background:#F8FAFC;border:1.5px solid #E2E8F0;border-radius:10px;padding:14px 12px;text-align:center}
.card-val{font-size:24px;font-weight:800;font-family:'JetBrains Mono',monospace;line-height:1;margin-bottom:3px}
.card-lbl{font-size:9.5px;font-weight:600;color:#94A3B8;letter-spacing:.8px;text-transform:uppercase}

/* Bars */
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.col-lbl{font-size:10px;font-weight:700;letter-spacing:.9px;text-transform:uppercase;color:#94A3B8;margin-bottom:12px}
.bar-row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.bar-lbl{width:68px;font-size:11px;font-weight:700;text-align:right;flex-shrink:0}
.bar-track{flex:1;height:9px;background:#F1F5F9;border-radius:999px;overflow:hidden}
.bar-fill{height:100%;border-radius:999px}
.bar-num{width:28px;text-align:right;font-size:11.5px;font-weight:700;font-family:'JetBrains Mono',monospace;flex-shrink:0}
.cat-item{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.cat-ico{font-size:13px;width:18px;text-align:center;flex-shrink:0}
.cat-name{width:130px;font-size:11.5px;font-weight:600;color:#334155;flex-shrink:0}
.cat-bar-track{flex:1;height:7px;background:#F1F5F9;border-radius:999px;overflow:hidden}
.cat-bar-fill{height:100%;border-radius:999px;background:#6366F1}
.cat-num{width:24px;text-align:right;font-size:11px;font-weight:700;color:#6366F1;font-family:'JetBrains Mono',monospace}

/* ── Fix Modal ── */
.modal-overlay{position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:1000;display:none;align-items:center;justify-content:center;padding:24px;backdrop-filter:blur(3px)}
.modal-overlay.open{display:flex}
.modal{background:#fff;border-radius:14px;width:100%;max-width:960px;max-height:90vh;display:flex;flex-direction:column;box-shadow:0 24px 60px rgba(15,23,42,.25);border:1.5px solid #E2E8F0;overflow:hidden}
.modal-hd{padding:16px 20px;border-bottom:1.5px solid #F1F5F9;display:flex;align-items:flex-start;gap:12px}
.modal-hd-info{flex:1;min-width:0}
.modal-issue-title{font-size:15px;font-weight:700;color:#0F172A;margin-bottom:6px;line-height:1.3}
.modal-badges{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.modal-close{width:30px;height:30px;border-radius:8px;background:#F1F5F9;border:none;cursor:pointer;color:#64748B;font-size:18px;display:flex;align-items:center;justify-content:center;transition:all .12s;flex-shrink:0;margin-top:-2px}
.modal-close:hover{background:#E2E8F0;color:#0F172A}
.modal-desc{padding:12px 20px;background:#F8FAFC;border-bottom:1.5px solid #F1F5F9;font-size:12.5px;color:#475569;line-height:1.6}
.modal-body{flex:1;display:grid;grid-template-columns:1fr 1fr;min-height:0;overflow:hidden}
.code-pane{display:flex;flex-direction:column;min-height:0;overflow:hidden}
.code-pane:first-child{border-right:1.5px solid #F1F5F9}
.pane-hd{padding:10px 16px;background:#F8FAFC;border-bottom:1px solid #F1F5F9;display:flex;align-items:center;gap:8px;flex-shrink:0}
.pane-title{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;flex:1}
.pane-title.orig{color:#DC2626}
.pane-title.fix{color:#16A34A}
.pane-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.code-scroll{overflow:auto;flex:1}
pre.code-block{font-family:'JetBrains Mono',monospace;font-size:11.5px;line-height:1.7;background:#0F172A;color:#CBD5E1;padding:0;margin:0}
.code-line{display:flex;padding:0 12px}
.code-line.hl{background:rgba(220,38,38,.18)}
.code-line.hl .code-txt{color:#FCA5A5}
.code-line-num{width:36px;text-align:right;color:#475569;flex-shrink:0;user-select:none;font-size:10.5px;padding-right:12px;padding-top:0}
.code-line.hl .code-line-num{color:#F87171}
.code-txt{white-space:pre;color:inherit}
.fix-pane-body{padding:16px 20px;font-size:12.5px;color:#1E293B;line-height:1.7;background:#FAFFFE;overflow:auto;flex:1}
.fix-pane-body code{font-family:'JetBrains Mono',monospace;font-size:11.5px;background:#F0FDF4;border:1px solid #BBF7D0;border-radius:4px;padding:1px 5px;color:#15803D}
.fix-code-block{background:#0F172A;border-radius:8px;padding:14px 16px;font-family:'JetBrains Mono',monospace;font-size:11.5px;color:#86EFAC;line-height:1.7;margin-top:10px;overflow-x:auto;white-space:pre;border:1.5px solid #14532D}
.no-code-msg{padding:20px;color:#94A3B8;font-size:12px;text-align:center;font-style:italic}
.modal-ft{padding:12px 20px;border-top:1.5px solid #F1F5F9;display:flex;justify-content:space-between;align-items:center;background:#FAFBFF}
.modal-file-path{font-size:10.5px;color:#94A3B8;font-family:'JetBrains Mono',monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:70%}
.modal-close-btn{padding:6px 14px;border-radius:7px;background:#F1F5F9;color:#475569;font-size:12px;font-weight:600;cursor:pointer;border:1.5px solid #E2E8F0;transition:all .12s}
.modal-close-btn:hover{background:#E2E8F0}

@media print{.topbar{position:static}.print-btn{display:none}.modal-overlay{display:none!important}.sidebar{display:none}.layout{display:block}.main{padding:0}.tree-children{display:block!important}.tree-arrow{display:none}}
@media(max-width:900px){.sidebar{display:none}.two-col{grid-template-columns:1fr}.modal-body{grid-template-columns:1fr}.code-pane:first-child{border-right:none;border-bottom:1.5px solid #F1F5F9}}
"""

issues_cat_html = ""
# collect categories from bugs
from collections import Counter
cat_counts = Counter(b['bug_category'] for b in bugs)
cat_total = len(bugs)
for cat, cnt in sorted(cat_counts.items(), key=lambda x:-x[1]):
    lbl = CAT_LBL.get(cat, cat.replace('_',' ').title())
    ico = CAT_ICO.get(cat,'🔍')
    pct = round(cnt/max(cat_total,1)*100)
    issues_cat_html += f'<div class="cat-item"><span class="cat-ico">{ico}</span><span class="cat-name">{lbl}</span><div class="cat-bar-track"><div class="cat-bar-fill" style="width:{pct}%"></div></div><span class="cat-num">{cnt}</span></div>'

def bar(label, count, color):
    w = max(2, round(count/max(total,1)*100)) if count else 0
    return f'<div class="bar-row"><div class="bar-lbl" style="color:{color}">{label}</div><div class="bar-track"><div class="bar-fill" style="width:{w}%;background:{color}"></div></div><div class="bar-num" style="color:{color}">{count}</div></div>'

unique_files = len(bugs_by_file)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PrismAI — Code Analysis Report</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>

<!-- Topbar -->
<div class="topbar">
  <div class="brand">
    <div class="brand-mark">
      <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2"/>
        <line x1="12" y1="2" x2="12" y2="22"/>
        <line x1="2" y1="8.5" x2="22" y2="8.5"/>
        <line x1="2" y1="15.5" x2="22" y2="15.5"/>
      </svg>
    </div>
    <div>
      <div class="brand-name">PrismAI</div>
      <div class="brand-sub">Code Analyzer</div>
    </div>
  </div>
  <div class="tb-div"></div>
  <span class="tb-date">Report generated <b>{now}</b></span>
  <div class="tb-spacer"></div>
  <span class="sev-pill" style="background:#FEF2F2;color:#DC2626;border-color:#FECACA">{crit} Critical</span>
  <span class="sev-pill" style="background:#FFF7ED;color:#EA580C;border-color:#FED7AA">{high} High</span>
  <span class="sev-pill" style="background:#FFFBEB;color:#D97706;border-color:#FDE68A">{med} Medium</span>
  <span class="sev-pill" style="background:#EFF6FF;color:#2563EB;border-color:#BFDBFE">{low} Low</span>
  <button class="print-btn" onclick="window.print()">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
    Print / Save PDF
  </button>
</div>

<!-- Layout -->
<div class="layout">

  <!-- Sidebar: file tree -->
  <div class="sidebar">
    <div class="sb-hd">
      <span class="sb-title">File Tree</span>
      <span class="sb-count">{unique_files} files</span>
    </div>

    <!-- Stats strip -->
    <div class="stats-strip">
      <div class="stat-cell"><div class="stat-num" style="color:#DC2626">{crit}</div><div class="stat-lbl">Critical</div></div>
      <div class="stat-cell"><div class="stat-num" style="color:#EA580C">{high}</div><div class="stat-lbl">High</div></div>
      <div class="stat-cell"><div class="stat-num" style="color:#D97706">{med}</div><div class="stat-lbl">Medium</div></div>
      <div class="stat-cell"><div class="stat-num" style="color:#2563EB">{low}</div><div class="stat-lbl">Low</div></div>
    </div>

    <!-- Health -->
    <div class="health-bar">
      <div class="health-row">
        <span class="health-lbl">Health Score</span>
        <span class="health-val" style="color:{health_color}">{health}/100</span>
      </div>
      <div class="health-track"><div class="health-fill" style="width:{health}%;background:{health_color}"></div></div>
    </div>

    <!-- Tree -->
    <div class="tree-wrap" id="tree-root">
      {tree_html}
    </div>
  </div>

  <!-- Main -->
  <div class="main">
    <div class="page-title">Code Analysis Report</div>
    <div class="page-sub">AI-powered bug detection &nbsp;·&nbsp; {total} issues across {unique_files} files &nbsp;·&nbsp; Gemini 2.5 Flash</div>

    <!-- Summary -->
    <div class="section">
      <div class="sec-hd">
        <span class="sec-hd-icon">📊</span>
        <span class="sec-title">Executive Summary</span>
        <span class="sec-sub">Health: <b style="color:{health_color}">{health}/100</b></span>
      </div>
      <div class="sec-body">
        <div class="cards">
          <div class="card"><div class="card-val" style="color:#6366F1">{total}</div><div class="card-lbl">Total Issues</div></div>
          <div class="card"><div class="card-val" style="color:#DC2626">{crit}</div><div class="card-lbl">Critical</div></div>
          <div class="card"><div class="card-val" style="color:#EA580C">{high}</div><div class="card-lbl">High</div></div>
          <div class="card"><div class="card-val" style="color:#D97706">{med}</div><div class="card-lbl">Medium</div></div>
          <div class="card"><div class="card-val" style="color:#2563EB">{low}</div><div class="card-lbl">Low</div></div>
          <div class="card"><div class="card-val" style="color:{health_color}">{health}</div><div class="card-lbl">Health Score</div></div>
          <div class="card"><div class="card-val" style="color:#16A34A">{stats['fixed_cnt']}</div><div class="card-lbl">Fixed</div></div>
          <div class="card"><div class="card-val" style="color:#94A3B8">{stats['ignored_cnt']}</div><div class="card-lbl">Ignored</div></div>
        </div>
      </div>
    </div>

    <!-- Breakdown -->
    <div class="section">
      <div class="sec-hd">
        <span class="sec-hd-icon">📈</span>
        <span class="sec-title">Issue Breakdown</span>
      </div>
      <div class="sec-body">
        <div class="two-col">
          <div>
            <div class="col-lbl">By Severity</div>
            {bar('CRITICAL', crit, '#DC2626')}
            {bar('HIGH', high, '#EA580C')}
            {bar('MEDIUM', med, '#D97706')}
            {bar('LOW', low, '#2563EB')}
          </div>
          <div>
            <div class="col-lbl">By Category</div>
            {issues_cat_html}
          </div>
        </div>
      </div>
    </div>

    <!-- How to use -->
    <div class="section">
      <div class="sec-hd">
        <span class="sec-hd-icon">💡</span>
        <span class="sec-title">How to use this report</span>
      </div>
      <div class="sec-body" style="color:#64748B;font-size:12.5px;line-height:1.8">
        Use the <b style="color:#0F172A">file tree on the left</b> to navigate files — click any file to expand its issues.
        Issues marked in <b style="color:#DC2626">red</b> are Critical/High priority.
        Click <b style="color:#6366F1">View Fix</b> on any issue to see the original code at that line alongside the AI-suggested fix.
      </div>
    </div>

  </div><!-- /main -->
</div><!-- /layout -->

<!-- Fix Modal -->
<div class="modal-overlay" id="fix-modal" onclick="closeModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <div class="modal-hd">
      <div class="modal-hd-info">
        <div class="modal-issue-title" id="m-title">Issue Title</div>
        <div class="modal-badges" id="m-badges"></div>
      </div>
      <button class="modal-close" onclick="closeFixModal()">×</button>
    </div>
    <div class="modal-desc" id="m-desc"></div>
    <div class="modal-body">
      <!-- Original code pane -->
      <div class="code-pane">
        <div class="pane-hd">
          <span class="pane-dot" style="background:#DC2626"></span>
          <span class="pane-title orig">Original Code</span>
          <span id="m-file-badge" style="font-size:10px;color:#94A3B8;font-family:'JetBrains Mono',monospace"></span>
        </div>
        <div class="code-scroll" id="m-code-scroll">
          <pre class="code-block" id="m-code"></pre>
        </div>
      </div>
      <!-- Fix suggestion pane -->
      <div class="code-pane">
        <div class="pane-hd">
          <span class="pane-dot" style="background:#16A34A"></span>
          <span class="pane-title fix">Suggested Fix</span>
        </div>
        <div class="fix-pane-body" id="m-fix"></div>
      </div>
    </div>
    <div class="modal-ft">
      <span class="modal-file-path" id="m-filepath"></span>
      <button class="modal-close-btn" onclick="closeFixModal()">Close</button>
    </div>
  </div>
</div>

<script>
// Issue data embedded at report generation time
const ISSUES = {issues_json};

function showFix(id) {{
  const issue = ISSUES.find(i => i.id === id);
  if (!issue) return;

  // Header
  document.getElementById('m-title').textContent = issue.title;
  const sc = issue.sev_color, sbg = issue.sev_bg, sbd = issue.sev_bd;
  document.getElementById('m-badges').innerHTML =
    `<span class="badge-sev" style="background:${{sbg}};color:${{sc}};border-color:${{sbd}}">${{issue.severity}}</span>` +
    `<span class="badge-cat">${{issue.cat_icon}} ${{issue.category}}</span>` +
    (issue.line ? `<span class="badge-ln">Line ${{issue.line}}</span>` : '') +
    `<span class="badge-conf">${{issue.confidence}}% confidence</span>`;

  document.getElementById('m-desc').textContent = issue.description;
  document.getElementById('m-filepath').textContent = issue.file_path || issue.file_name;

  const fileBadge = document.getElementById('m-file-badge');
  fileBadge.textContent = issue.file_name + (issue.line ? ':' + issue.line : '');

  // Code pane
  const codeEl = document.getElementById('m-code');
  if (issue.snippet && issue.snippet.length) {{
    codeEl.innerHTML = issue.snippet.map(l => {{
      const lineNumHtml = `<span class="code-line-num">${{l.num}}</span>`;
      const codeTxt = `<span class="code-txt">${{escHtml(l.code)}}</span>`;
      return `<div class="code-line${{l.highlight ? ' hl' : ''}}">${{lineNumHtml}}${{codeTxt}}</div>`;
    }}).join('');
    // Scroll to highlighted line
    setTimeout(() => {{
      const hl = codeEl.querySelector('.hl');
      if (hl) hl.scrollIntoView({{block:'center'}});
    }}, 50);
  }} else {{
    codeEl.innerHTML = '<div class="no-code-msg">Source file not available at report generation time.</div>';
  }}

  // Fix pane
  const fixEl = document.getElementById('m-fix');
  if (issue.fix_suggestion) {{
    const text = issue.fix_suggestion;
    // Detect inline code blocks (backtick) and format
    let formatted = escHtml(text);
    // Bold inline code `...`
    formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Detect multi-line code blocks starting with common patterns
    const codePatterns = [
      /(\s|^)((?:def |function |const |let |var |if |return |import |export |class |async |await |try |catch |for |while ).+)/g
    ];
    fixEl.innerHTML = `<div style="margin-bottom:12px;font-weight:500;color:#0F172A;">💡 AI Suggestion</div>
      <div style="line-height:1.75">${{formatted}}</div>`;
  }} else {{
    fixEl.innerHTML = '<div class="no-code-msg">No fix suggestion available.</div>';
  }}

  document.getElementById('fix-modal').classList.add('open');
  document.body.style.overflow = 'hidden';
}}

function closeFixModal() {{
  document.getElementById('fix-modal').classList.remove('open');
  document.body.style.overflow = '';
}}

function closeModal(e) {{
  if (e.target === document.getElementById('fix-modal')) closeFixModal();
}}

document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeFixModal(); }});

function toggleNode(id) {{
  const el = document.getElementById(id);
  const arr = document.getElementById('arr-' + id);
  if (!el) return;
  const isOpen = el.style.display !== 'none';
  el.style.display = isOpen ? 'none' : 'block';
  if (arr) arr.classList.toggle('open', !isOpen);
}}

function escHtml(s) {{
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

// Auto-expand first 2 folders for quick overview
(function() {{
  const rows = document.querySelectorAll('.tree-folder');
  let expanded = 0;
  rows.forEach(r => {{
    if (expanded >= 2) return;
    const onclick = r.getAttribute('onclick');
    if (onclick) {{
      const id = onclick.match(/toggleNode\('([^']+)'\)/)?.[1];
      if (id) {{ toggleNode(id); expanded++; }}
    }}
  }});
}})();
</script>
</body>
</html>"""

out = 'static_report.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(html)

size = os.path.getsize(out)
print(f"Report written: {os.path.abspath(out)}")
print(f"Size: {size:,} bytes ({size//1024} KB)")
print(f"Bugs: {len(bugs)} | Files: {unique_files} | Categories: {len(cat_counts)}")
