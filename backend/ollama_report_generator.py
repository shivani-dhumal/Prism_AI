"""
report_generator.py
Generates a self-contained HTML code viewer with error highlighting.
Reads from MySQL database + source files and produces code_report.html
"""

import os
import sys
import re
import json
import html as html_lib
import mysql.connector

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import DB_CONFIG, TARGET_DIRECTORY


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


# ─────────────────────────────────────────────
#  DB QUERIES
# ─────────────────────────────────────────────

def load_all_data():
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT f.id, f.file_name, f.file_path, f.extension,
               COALESCE(ff.api_flags,'')       AS api_flags,
               COALESCE(ff.complexity_flags,'') AS complexity_flags,
               COALESCE(ff.pattern_flags,'')   AS pattern_flags,
               COALESCE(ff.risk_flags,'')       AS risk_flags,
               COALESCE(ff.ui_flags,'')         AS ui_flags,
               COALESCE(ff.api_count,0)         AS api_count,
               COALESCE(ff.loc,0)               AS loc
        FROM files f
        LEFT JOIN file_flags ff ON ff.file_id = f.id
        WHERE f.extension IN ('vue','js','ts','go')
        ORDER BY f.file_name
    """)
    files = cur.fetchall()

    cur.execute("SELECT * FROM accessibility_report  WHERE status='FAIL'")
    acc = cur.fetchall()

    cur.execute("SELECT * FROM ui_consistency_report WHERE status='FAIL'")
    ui  = cur.fetchall()

    # cur.execute("""
    #     SELECT cc.*, c.file_id, f.file_path
    #     FROM component_complexity cc
    #     JOIN components c ON c.id = cc.component_id
    #     JOIN files      f ON f.id  = c.file_id
    #     WHERE cc.flags IS NOT NULL AND cc.flags <> ''
    # """)
    # complexity = cur.fetchall()
    complexity = []

    cur.execute("""
        SELECT a.*, f.file_path
        FROM apis a
        JOIN files f ON f.id = a.file_id
    """)
    apis = cur.fetchall()

    cur.close()
    conn.close()
    return files, acc, ui, complexity, apis


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def read_source(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception:
        return None


def find_line(content, search_terms):
    """Return 1-based line number of first term found, or None."""
    if not content or not search_terms:
        return None
    lines = content.splitlines()
    for term in search_terms:
        if not term or len(term) < 3:
            continue
        for i, line in enumerate(lines, 1):
            if term.lower() in line.lower():
                return i
    return None


def terms_from_result(actual_result):
    """Extract searchable tokens from an error description string."""
    terms = []
    # CSS class like class='eye-abs'
    for m in re.finditer(r"class=['\"]([^'\"]+)['\"]", actual_result):
        terms += m.group(1).split()
    # id like id='updateAndSave'
    for m in re.finditer(r"id=['\"]([^'\"]+)['\"]", actual_result):
        terms.append(m.group(1))
    # tag+class shorthand like <div class='alert'>
    for m in re.finditer(r"<\w+[^>]*class=['\"]([^'\"]+)['\"]", actual_result):
        terms += m.group(1).split()[:2]
    # bare tag name
    for m in re.finditer(r"<(\w+)", actual_result):
        terms.append(m.group(1))
    # quoted words (function names, keys, etc.)
    for m in re.finditer(r"'([a-zA-Z_][\w./-]{2,})'", actual_result):
        terms.append(m.group(1))
    return terms


SEV_ORDER = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}

def severity_color(sev):
    return {'HIGH': '#ef4444', 'MEDIUM': '#f59e0b', 'LOW': '#3b82f6'}.get(sev, '#6b7280')

def severity_bg(sev):
    return {'HIGH': 'rgba(239,68,68,.08)', 'MEDIUM': 'rgba(245,158,11,.07)', 'LOW': 'rgba(59,130,246,.07)'}.get(sev, 'transparent')

TYPE_ICON = {
    'accessibility': '♿',
    'ui':            '🎨',
    'complexity':    '📐',
    'flag':          '🚩',
    'api':           '🔗',
}
TYPE_COLOR = {
    'accessibility': '#8b5cf6',
    'ui':            '#06b6d4',
    'complexity':    '#f59e0b',
    'flag':          '#ef4444',
    'api':           '#10b981',
}


# ─────────────────────────────────────────────
#  BUILD ERROR MAP
# ─────────────────────────────────────────────

def build_error_map(files, acc, ui, complexity, apis):
    content_cache = {}

    def cached_content(fp):
        if fp not in content_cache:
            content_cache[fp] = read_source(fp)
        return content_cache[fp]

    def add(error_map, fp, line, etype, rule, message, sev):
        error_map.setdefault(fp, []).append({
            'line': line, 'type': etype,
            'rule': rule, 'message': message, 'severity': sev
        })

    error_map = {}

    for issue in acc:
        fp = issue['file_path']
        terms = terms_from_result(issue['actual_result'])
        line  = find_line(cached_content(fp), terms)
        add(error_map, fp, line, 'accessibility',
            issue['rule_name'], issue['actual_result'], issue['severity'])

    for issue in ui:
        fp = issue['file_path']
        terms = terms_from_result(issue['actual_result'])
        line  = find_line(cached_content(fp), terms)
        add(error_map, fp, line, 'ui',
            issue['rule_name'], issue['actual_result'],
            issue.get('severity', 'MEDIUM'))

    for issue in complexity:
        fp = issue['file_path']
        flag_str = issue['flags']
        sev = 'HIGH' if 'VERY_LARGE' in flag_str else 'MEDIUM'
        add(error_map, fp, 1, 'complexity',
            'Component Complexity',
            f"{flag_str} — {issue['totallines']} total lines, "
            f"{issue['methods']} methods, {issue['template_lines']} template lines",
            sev)

    file_map = {f['id']: f for f in files}
    for f in files:
        fp = f['file_path']
        all_flags = ', '.join(
            filter(None, [f['api_flags'], f['complexity_flags'],
                          f['pattern_flags'], f['risk_flags'], f['ui_flags']])
        )
        if all_flags.strip():
            for flag in all_flags.split(','):
                flag = flag.strip()
                if flag:
                    add(error_map, fp, None, 'flag', 'Code Flag', flag, 'MEDIUM')

    # api errors grouped per file
    api_by_file = {}
    for a in apis:
        api_by_file.setdefault(a['file_path'], []).append(a)
    for fp, calls in api_by_file.items():
        content = cached_content(fp)
        for call in calls:
            url = call['url'] or ''
            line = find_line(content, [url.split('/')[-1], url.split('/')[-2] if '/' in url else None])
            add(error_map, fp, line, 'api', f"{call['method']} API Call",
                f"{call['method']} {url}", 'LOW')

    return error_map, content_cache


# ─────────────────────────────────────────────
#  SYNTAX HIGHLIGHT (simple regex, no deps)
# ─────────────────────────────────────────────

VUE_KEYWORDS  = r'\b(import|export|default|from|const|let|var|function|return|if|else|for|while|new|this|async|await|class|extends|typeof|null|undefined|true|false)\b'
HTML_TAGS     = r'(&lt;\/?)([\w-]+)'
HTML_ATTRS    = r'\s([\w:@.-]+)(=)'
STRINGS       = r'(&quot;[^&]*&quot;|&#39;[^&]*&#39;|`[^`]*`)'
COMMENTS      = r'(\/\/[^\n]*|\/\*[\s\S]*?\*\/|&lt;!--[\s\S]*?--&gt;)'
NUMBERS       = r'\b(\d+\.?\d*)\b'
VUE_SECTIONS  = r'(&lt;(template|script|style)(?:\s[^&]*)?\s*&gt;)'
VUE_CLOSE     = r'(&lt;\/(template|script|style)&gt;)'


def syntax_highlight(code, ext):
    escaped = html_lib.escape(code)

    def repl_comments(m):
        return f'<span class="tok-cmt">{m.group(0)}</span>'
    def repl_strings(m):
        return f'<span class="tok-str">{m.group(0)}</span>'
    def repl_kw(m):
        return f'<span class="tok-kw">{m.group(0)}</span>'
    def repl_tag(m):
        return f'{m.group(1)}<span class="tok-tag">{m.group(2)}</span>'
    def repl_attr(m):
        return f' <span class="tok-attr">{m.group(1)}</span>{m.group(2)}'
    def repl_num(m):
        return f'<span class="tok-num">{m.group(0)}</span>'
    def repl_section(m):
        return f'<span class="tok-section">{m.group(0)}</span>'

    escaped = re.sub(COMMENTS,     repl_comments, escaped)
    escaped = re.sub(STRINGS,      repl_strings,  escaped)
    escaped = re.sub(VUE_SECTIONS, repl_section,  escaped)
    escaped = re.sub(VUE_CLOSE,    repl_section,  escaped)
    escaped = re.sub(HTML_TAGS,    repl_tag,      escaped)
    escaped = re.sub(HTML_ATTRS,   repl_attr,     escaped)
    escaped = re.sub(VUE_KEYWORDS, repl_kw,       escaped)
    escaped = re.sub(NUMBERS,      repl_num,      escaped)
    return escaped


# ─────────────────────────────────────────────
#  HTML GENERATION
# ─────────────────────────────────────────────

CSS = """
:root {
  --bg: #f5f7fb; --sidebar: #ffffff; --panel: #f5f7fb;
  --border: #dde2ee; --border2: #c8d0e4;
  --text: #1a2035; --text2: #4a5278; --muted: #7a86a8;
  --line-bg: #f0f3f9; --line-hover: #e8ecf5;
  --hl-acc: rgba(255,77,109,.10); --hl-warn: rgba(255,140,66,.12);
  --hl-info: rgba(6,214,160,.10);
  --accent: #6c8fff; --accent2: #a78bfa;
  --crit: #ff4d6d; --high: #ff8c42; --med: #ffd166; --low: #06d6a0;
  --spell: #c084fc; --fp: #a78bfa;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'DM Sans','IBM Plex Mono',system-ui,sans-serif;background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column;overflow:hidden}

/* ── TOP BAR ── */
#topbar{display:flex;align-items:center;gap:12px;padding:0 20px;height:52px;background:var(--sidebar);border-bottom:1px solid var(--border);flex-shrink:0}
#topbar h1{font-family:'Syne',sans-serif;font-size:15px;font-weight:800;color:var(--text);letter-spacing:-.02em}
#topbar h1 em{font-style:normal;color:var(--accent)}
#topbar .stats{margin-left:auto;display:flex;gap:8px}
.stat-pill{font-size:11px;padding:4px 10px;border-radius:20px;font-weight:600}
.sp-red{background:rgba(255,77,109,.1);color:var(--crit);border:1px solid rgba(255,77,109,.3)}
.sp-yellow{background:rgba(255,140,66,.1);color:var(--high);border:1px solid rgba(255,140,66,.3)}
.sp-blue{background:rgba(6,214,160,.08);color:var(--low);border:1px solid rgba(6,214,160,.25)}
.sp-green{background:rgba(192,132,252,.1);color:var(--spell);border:1px solid rgba(192,132,252,.3)}
#search{background:var(--line-bg);border:1px solid var(--border);color:var(--text);font-family:'IBM Plex Mono',monospace;font-size:11px;padding:5px 10px;border-radius:6px;width:180px;outline:none}
#search:focus{border-color:var(--accent);box-shadow:0 0 0 2px rgba(108,143,255,.15)}
#filter-bar{display:flex;gap:4px}
.fb{font-size:11px;padding:3px 10px;border-radius:4px;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;font-family:inherit;transition:all .15s}
.fb.active,.fb:hover{background:var(--accent);color:#fff;border-color:var(--accent)}

/* ── LAYOUT ── */
#main{display:flex;flex:1;overflow:hidden}

/* ── SIDEBAR ── */
#sidebar{width:280px;flex-shrink:0;background:var(--sidebar);border-right:1px solid var(--border);overflow-y:auto;font-size:12px;padding:8px}
#sidebar::-webkit-scrollbar{width:3px}
#sidebar::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}
.folder-header{font-size:9px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);padding:12px 10px 5px;display:flex;align-items:center;gap:6px}
.folder-header::after{content:'';flex:1;height:1px;background:var(--border)}
.file-item{display:flex;align-items:center;gap:10px;padding:8px 10px;cursor:pointer;border-radius:6px;transition:background .15s;margin-bottom:2px}
.file-item:hover{background:var(--line-hover)}
.file-item.active{background:var(--line-bg);box-shadow:inset 0 0 0 1px var(--border2)}
.file-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text);font-family:'IBM Plex Mono',monospace;font-size:11.5px;font-weight:500}
.file-ext{font-size:9px;padding:2px 5px;border-radius:3px;font-weight:600;background:var(--line-bg);color:var(--muted);border:1px solid var(--border)}
.file-ext.vue{background:rgba(6,214,160,.08);color:#059669;border-color:rgba(6,214,160,.25)}
.file-ext.js{background:rgba(255,209,102,.08);color:#b45309;border-color:rgba(255,209,102,.3)}
.file-ext.ts{background:rgba(108,143,255,.08);color:#4f6df5;border-color:rgba(108,143,255,.3)}
.file-ext.go{background:rgba(167,139,250,.08);color:#7c3aed;border-color:rgba(167,139,250,.3)}
.err-count{font-size:8.5px;padding:2px 5px;border-radius:3px;font-weight:700;flex-shrink:0;letter-spacing:.04em}
.ec-red{background:rgba(255,77,109,.1);color:var(--crit);border:1px solid rgba(255,77,109,.3)}
.ec-yellow{background:rgba(255,140,66,.1);color:var(--high);border:1px solid rgba(255,140,66,.3)}
.ec-green{background:rgba(6,214,160,.08);color:var(--low);border:1px solid rgba(6,214,160,.25)}

/* ── CODE PANEL ── */
#code-wrap{flex:1;display:flex;flex-direction:column;overflow:hidden}
#file-header{padding:12px 24px;background:var(--sidebar);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;flex-shrink:0}
#file-path{font-size:11px;color:var(--muted);font-family:'IBM Plex Mono',monospace;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#file-stats{display:flex;gap:8px;font-size:11px;color:var(--muted);flex-shrink:0}
#code-area{flex:1;overflow:auto;position:relative;background:#f8fafc}
#code-area::-webkit-scrollbar{width:5px;height:5px}
#code-area::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px}
#no-file{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--muted);gap:12px;font-size:13px}
#no-file .icon{font-size:40px;opacity:.2}
table.code-table{width:100%;border-collapse:collapse}
.ln{width:52px;padding:0 12px 0 0;text-align:right;color:var(--muted);font-size:12px;user-select:none;vertical-align:top;padding-top:1px;font-family:'IBM Plex Mono',monospace}
.lc{padding:0 16px 0 8px;white-space:pre;font-size:12px;line-height:1.75;width:100%;font-family:'IBM Plex Mono',monospace;color:#24292f}
.code-row:hover .ln{color:var(--text2)}
.code-row:hover .lc{background:var(--line-hover)}
.code-row.hl-high .lc{background:var(--hl-acc)!important;border-left:3px solid var(--crit)}
.code-row.hl-medium .lc{background:var(--hl-warn)!important;border-left:3px solid var(--high)}
.code-row.hl-low .lc{background:var(--hl-info)!important;border-left:3px solid var(--low)}
.code-row.hl-api .lc{background:rgba(6,214,160,.07)!important;border-left:3px solid var(--low)}

/* error marker inline */
.err-marker{display:inline-flex;align-items:center;gap:4px;margin-left:14px;font-size:9.5px;padding:1px 7px;border-radius:3px;vertical-align:middle;font-family:'DM Sans',sans-serif;font-weight:700;letter-spacing:.03em;cursor:pointer}
.em-high{background:rgba(255,77,109,.1);color:var(--crit);border:1px solid rgba(255,77,109,.3)}
.em-medium{background:rgba(255,140,66,.1);color:var(--high);border:1px solid rgba(255,140,66,.3)}
.em-low{background:rgba(6,214,160,.08);color:var(--low);border:1px solid rgba(6,214,160,.25)}
.em-api{background:rgba(6,214,160,.08);color:var(--low);border:1px solid rgba(6,214,160,.25)}

/* ── ERROR PANEL ── */
#error-panel{height:200px;flex-shrink:0;background:var(--sidebar);border-top:1px solid var(--border);overflow-y:auto}
#ep-header{padding:8px 24px;font-size:10px;font-weight:700;color:var(--muted);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;letter-spacing:.08em;text-transform:uppercase;position:sticky;top:0;background:var(--sidebar);z-index:1}
.ep-row{display:flex;align-items:flex-start;gap:10px;padding:8px 24px;border-bottom:1px solid var(--line-bg);font-size:12px;cursor:pointer;transition:background .15s}
.ep-row:hover{background:var(--line-hover)}
.ep-icon{font-size:14px;flex-shrink:0;width:18px;text-align:center;margin-top:1px}
.ep-body{flex:1;min-width:0}
.ep-rule{font-weight:600;color:var(--text);font-size:12px}
.ep-msg{color:var(--muted);margin-top:2px;word-break:break-word;line-height:1.5;font-size:11px}
.ep-line{font-size:9.5px;padding:2px 6px;border-radius:3px;flex-shrink:0;margin-top:2px;color:var(--muted);background:var(--line-bg);border:1px solid var(--border);font-family:'IBM Plex Mono',monospace}
.ep-sev{font-size:9px;padding:2px 6px;border-radius:3px;flex-shrink:0;font-weight:700;letter-spacing:.04em}

/* syntax tokens */
.tok-kw{color:#0550ae}.tok-str{color:#116329}.tok-cmt{color:#6e7781;font-style:italic}
.tok-tag{color:#cf222e}.tok-attr{color:#953800}.tok-num{color:#953800}
.tok-section{color:#6f42c1;font-weight:600}

/* scrollbar */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--muted)}

@media(max-width:900px){#sidebar{width:220px}}
"""

JS = """
const FILES = window.__FILES__;
let currentFile = null;
let currentFilter = 'all';

const sidebar    = document.getElementById('sidebar');
const codeArea   = document.getElementById('code-area');
const noFile     = document.getElementById('no-file');
const fileHeader = document.getElementById('file-header');
const filePath   = document.getElementById('file-path');
const fileStats  = document.getElementById('file-stats');
const errorPanel = document.getElementById('error-panel');
const epHeader   = document.getElementById('ep-header');
const searchEl   = document.getElementById('search');

function buildSidebar(filterText) {
  sidebar.innerHTML = '';
  const folders = {};
  FILES.forEach(f => {
    const parts = f.path.replace(/\\\\/g,'/').split('/');
    const folder = parts.slice(-3,-1).join('/') || 'root';
    (folders[folder] = folders[folder]||[]).push(f);
  });
  Object.entries(folders).forEach(([folder, flist]) => {
    const filtered = flist.filter(f =>
      !filterText || f.name.toLowerCase().includes(filterText.toLowerCase())
    );
    if (!filtered.length) return;
    const hdr = document.createElement('div');
    hdr.className = 'folder-header'; hdr.textContent = folder;
    sidebar.appendChild(hdr);
    filtered.forEach(f => {
      const ec = f.errors.length;
      const maxSev = ec ? f.errors.reduce((a,b)=>
        ({HIGH:0,MEDIUM:1,LOW:2}[a.severity]||3) < ({HIGH:0,MEDIUM:1,LOW:2}[b.severity]||3) ? a : b
      ).severity : 'none';
      const div = document.createElement('div');
      div.className = 'file-item' + (currentFile===f.path?' active':'');
      div.dataset.path = f.path;
      div.innerHTML = `
        <span class="file-ext ${f.ext}">${f.ext}</span>
        <span class="file-name" title="${f.path}">${f.name}</span>
        ${ec ? `<span class="err-count ${maxSev==='HIGH'?'ec-red':maxSev==='MEDIUM'?'ec-yellow':'ec-green'}">${ec}</span>` : ''}
      `;
      div.addEventListener('click', () => openFile(f.path));
      sidebar.appendChild(div);
    });
  });
}

function scrollToLine(lineNum) {
  const row = document.querySelector(`.code-row[data-line="${lineNum}"]`);
  if (row) {
    row.scrollIntoView({behavior:'smooth', block:'center'});
    row.style.outline = '1px solid #58a6ff';
    setTimeout(()=>row.style.outline='', 1200);
  }
}

function openFile(path) {
  currentFile = path;
  const f = FILES.find(x => x.path === path);
  if (!f) return;

  document.querySelectorAll('.file-item').forEach(el => {
    el.classList.toggle('active', el.dataset.path === path);
  });

  noFile.style.display = 'none';
  fileHeader.style.display = 'flex';

  const shortPath = path.replace(/\\\\/g,'/').split('/').slice(-4).join('/');
  filePath.textContent = shortPath;

  const errTypes = [...new Set(f.errors.map(e=>e.type))];
  fileStats.innerHTML = `
    <span>${f.loc} lines</span>
    ${f.errors.length ? `<span style="color:#f87171">${f.errors.length} issue${f.errors.length!==1?'s':''}</span>` : '<span style="color:#6ee7b7">✓ clean</span>'}
    <span>${f.ext}</span>
  `;

  // Build error index by line
  const errByLine = {};
  f.errors.forEach(e => {
    if (e.line) {
      (errByLine[e.line] = errByLine[e.line]||[]).push(e);
    }
  });

  // Filter errors for current type filter
  const filtered = currentFilter === 'all'
    ? f.errors
    : f.errors.filter(e => e.type === currentFilter);

  const filtErrByLine = {};
  filtered.forEach(e => {
    if (e.line) (filtErrByLine[e.line] = filtErrByLine[e.line]||[]).push(e);
  });

  // Build code table
  const lines = f.highlighted.split('\\n');
  let tableHtml = '<table class="code-table"><tbody>';
  lines.forEach((lineHtml, i) => {
    const ln = i + 1;
    const errs = filtErrByLine[ln] || [];
    const maxSev = errs.reduce((a,b)=>
      ({HIGH:0,MEDIUM:1,LOW:2}[a.severity]||3) < ({HIGH:0,MEDIUM:1,LOW:2}[b.severity]||3) ? a : b
    , {severity:'none'}).severity;

    const hlClass = errs.length
      ? (maxSev==='HIGH' ? 'hl-high' : maxSev==='MEDIUM' ? 'hl-medium' : maxSev==='LOW' ? 'hl-low' : '')
      : '';

    const markers = errs.map(e => {
      const cls = e.type==='api' ? 'em-api' : (maxSev==='HIGH'?'em-high':maxSev==='MEDIUM'?'em-medium':'em-low');
      return `<span class="err-marker ${cls}" title="${e.rule}">${TYPE_ICONS[e.type]||'⚑'} ${e.type}</span>`;
    }).join('');

    tableHtml += `<tr class="code-row ${hlClass}" data-line="${ln}"><td class="ln">${ln}</td><td class="lc">${lineHtml}${markers}</td></tr>`;
  });
  tableHtml += '</tbody></table>';
  codeArea.innerHTML = tableHtml;

  // Build error panel
  const epErrors = filtered.sort((a,b)=>
    ({HIGH:0,MEDIUM:1,LOW:2}[a.severity]||3) - ({HIGH:0,MEDIUM:1,LOW:2}[b.severity]||3)
  );
  epHeader.innerHTML = `Issues <span style="color:var(--text)">${epErrors.length}</span> &nbsp; <span style="color:var(--muted);font-size:10px;font-weight:400;text-transform:none">click a row to jump to line</span>`;

  let epHtml = '';
  epErrors.forEach(e => {
    const sevColor = {HIGH:'#f87171',MEDIUM:'#fbbf24',LOW:'#93c5fd'}[e.severity]||'#7d8590';
    const sevBg    = {HIGH:'rgba(239,68,68,.2)',MEDIUM:'rgba(245,158,11,.2)',LOW:'rgba(59,130,246,.2)'}[e.severity]||'transparent';
    const lineStr  = e.line ? `line ${e.line}` : 'file-level';
    epHtml += `<div class="ep-row" onclick="scrollToLine(${e.line||1})">
      <span class="ep-icon">${TYPE_ICONS[e.type]||'⚑'}</span>
      <div class="ep-body">
        <div class="ep-rule">${escHtml(e.rule)}</div>
        <div class="ep-msg">${escHtml(e.message)}</div>
      </div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0">
        <span class="ep-sev" style="background:${sevBg};color:${sevColor}">${e.severity}</span>
        <span class="ep-line">${lineStr}</span>
      </div>
    </div>`;
  });

  if (!epHtml) epHtml = '<div style="padding:16px;color:var(--muted);font-size:12px">No issues for this filter.</div>';
  errorPanel.innerHTML = epHeader.outerHTML + epHtml;
  // reattach header (it was re-built)
  document.getElementById('ep-header').id = 'ep-header';
}

const TYPE_ICONS = {accessibility:'♿',ui:'🎨',complexity:'📐',flag:'🚩',api:'🔗'};
function escHtml(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

// Filter buttons
document.querySelectorAll('.fb').forEach(btn => {
  btn.addEventListener('click', () => {
    currentFilter = btn.dataset.type;
    document.querySelectorAll('.fb').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    if (currentFile) openFile(currentFile);
  });
});

// Search
searchEl.addEventListener('input', () => buildSidebar(searchEl.value));

// Init
buildSidebar('');
// Auto-open first file with errors
const first = FILES.find(f=>f.errors.length) || FILES[0];
if (first) openFile(first.path);
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>ShivaniD · Audit View Review</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Syne:wght@600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap" rel="stylesheet"/>
<style>{CSS}</style>
</head>
<body>

<div id="topbar">
  <h1><em>ShivaniD</em> · Audit Review</h1>
  <input id="search" type="search" placeholder="Search files…">
  <div id="filter-bar">
    <button class="fb active" data-type="all">All</button>
    <button class="fb" data-type="accessibility">A11Y</button>
    <button class="fb" data-type="ui">UI</button>
    <button class="fb" data-type="flag">Flags</button>
    <button class="fb" data-type="api">APIs</button>
  </div>
  <div class="stats">
    <span class="stat-pill sp-red">{cnt_high} High</span>
    <span class="stat-pill sp-yellow">{cnt_med} Medium</span>
    <span class="stat-pill sp-blue">{cnt_low} Low</span>
    <span class="stat-pill sp-green">{cnt_files} Files</span>
  </div>
</div>

<div id="main">
  <div id="sidebar"></div>
  <div id="code-wrap">
    <div id="file-header" style="display:none">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" stroke-width="2" style="flex-shrink:0"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      <span id="file-path"></span>
      <div id="file-stats"></div>
    </div>
    <div id="code-area">
      <div id="no-file">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:.2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        <span>Select a file from the sidebar to inspect its audit issues</span>
      </div>
    </div>
    <div id="error-panel">
      <div id="ep-header">Issues</div>
    </div>
  </div>
</div>

<script>
window.__FILES__ = {FILES_JSON};
{JS}
</script>
</body>
</html>"""


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def generate_report(output_name=None):
    print("Loading data from database…")
    files, acc, ui, complexity, apis = load_all_data()

    print("Building error map…")
    error_map, content_cache = build_error_map(files, acc, ui, complexity, apis)

    print("Building file records…")
    file_data = []
    for f in files:
        fp   = f['file_path']
        content = content_cache.get(fp) or read_source(fp) or '// Source file not accessible from this machine'
        errors  = error_map.get(fp, [])
        highlighted = syntax_highlight(content, f['extension'])
        file_data.append({
            'id':   f['id'],
            'name': f['file_name'],
            'path': fp,
            'ext':  f['extension'],
            'loc':  f['loc'],
            'highlighted': highlighted,
            'errors': sorted(errors, key=lambda e: SEV_ORDER.get(e['severity'], 9)),
        })

    file_data.sort(key=lambda x: (-len(x['errors']), x['name']))

    cnt_high  = sum(1 for f in file_data for e in f['errors'] if e['severity']=='HIGH')
    cnt_med   = sum(1 for f in file_data for e in f['errors'] if e['severity']=='MEDIUM')
    cnt_low   = sum(1 for f in file_data for e in f['errors'] if e['severity']=='LOW')

    files_json = json.dumps(file_data, ensure_ascii=False)

    html = (HTML_TEMPLATE
        .replace('{CSS}',      CSS)
        .replace('{JS}',       JS)
        .replace('{FILES_JSON}', files_json)
        .replace('{cnt_high}', str(cnt_high))
        .replace('{cnt_med}',  str(cnt_med))
        .replace('{cnt_low}',  str(cnt_low))
        .replace('{cnt_files}',str(len(file_data)))
    )

    if output_name:
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_name)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    else:
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'code_report.html')

    with open(out_path, 'w', encoding='utf-8') as fout:
        fout.write(html)

    print(f"\n[OK] Report saved to: {out_path}")
    print(f"   Files scanned : {len(file_data)}")
    print(f"   HIGH issues   : {cnt_high}")
    print(f"   MEDIUM issues : {cnt_med}")
    print(f"   LOW issues    : {cnt_low}")


if __name__ == '__main__':
    generate_report()