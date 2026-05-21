"""
ChromaDB RAG Scanner Engine
============================
True Retrieval-Augmented Generation pipeline:
  1. A knowledge base of 50+ UI/UX / Accessibility / Security rules is
     embedded into a ChromaDB vector collection on first run.
  2. When a file is scanned, its code is used as a query to retrieve
     the TOP-K most relevant rules from ChromaDB.
  3. The retrieved rules + source code are sent to Gemini for analysis.
  4. Gemini returns structured JSON issues with fix suggestions.

This gives far more accurate, context-aware results than a static
prompt because the LLM sees only the rules relevant to each file.
"""

import os
import sys
import json
import time
import io
import hashlib

# Fix Windows console encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import chromadb
import google.generativeai as genai

# ─────────────────────────────────────────────
# Gemini setup
# ─────────────────────────────────────────────
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from config import GEMINI_API_KEY
except ImportError:
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"

_model = genai.GenerativeModel(
    MODEL_NAME,
    generation_config=genai.GenerationConfig(
        temperature=0.15,
        response_mime_type="application/json",
    ),
)

# ─────────────────────────────────────────────
# UI/UX Knowledge Base (embedded into ChromaDB)
# ─────────────────────────────────────────────
KNOWLEDGE_BASE = [
    # ── Accessibility ──
    {"id": "a11y_img_alt",       "category": "accessibility", "severity": "high",
     "rule": "All <img> tags must have a meaningful alt attribute for screen readers. Decorative images should use alt=\"\".",
     "tags": "img image alt attribute screen reader accessibility"},
    {"id": "a11y_aria_label",    "category": "accessibility", "severity": "high",
     "rule": "Icon-only buttons and links must have aria-label or aria-labelledby so assistive tech can describe them.",
     "tags": "button icon aria-label accessibility screen reader"},
    {"id": "a11y_form_label",    "category": "accessibility", "severity": "high",
     "rule": "Every form input must have an associated <label> element or aria-label. Placeholder is NOT a substitute for label.",
     "tags": "input form label placeholder accessibility"},
    {"id": "a11y_heading_order", "category": "accessibility", "severity": "medium",
     "rule": "Heading elements (h1-h6) must follow a logical hierarchy. Do not skip levels (e.g. h1 then h3).",
     "tags": "h1 h2 h3 heading hierarchy structure semantic"},
    {"id": "a11y_keyboard",      "category": "accessibility", "severity": "high",
     "rule": "Interactive elements with @click must also handle keyboard events (@keydown.enter, @keyup). Add tabindex=\"0\" for non-native interactive elements.",
     "tags": "click keydown keyboard tabindex focus interactive"},
    {"id": "a11y_color_contrast","category": "accessibility", "severity": "medium",
     "rule": "Text must have sufficient color contrast against its background (WCAG AA: 4.5:1 for normal text, 3:1 for large text).",
     "tags": "color contrast background text css wcag"},
    {"id": "a11y_aria_live",     "category": "accessibility", "severity": "medium",
     "rule": "Dynamic content updated via JavaScript/Vue reactivity should use aria-live regions so screen readers announce changes.",
     "tags": "aria-live dynamic content toast notification alert"},
    {"id": "a11y_focus_visible", "category": "accessibility", "severity": "medium",
     "rule": "Never use outline:none or outline:0 without providing an alternative focus indicator. Focus must be visible for keyboard users.",
     "tags": "outline focus visible keyboard css focus-visible"},
    {"id": "a11y_lang",          "category": "accessibility", "severity": "medium",
     "rule": "The <html> element must have a lang attribute specifying the page language for screen readers.",
     "tags": "html lang attribute language i18n"},
    {"id": "a11y_role",          "category": "accessibility", "severity": "medium",
     "rule": "Custom interactive widgets (dropdowns, modals, tabs) must have appropriate ARIA roles (role=\"dialog\", role=\"tabpanel\", etc.).",
     "tags": "role aria dialog modal tab widget custom"},

    # ── UI Consistency ──
    {"id": "ui_btn_style",       "category": "ui_consistency", "severity": "medium",
     "rule": "All buttons in the same context should use consistent styling — same padding, font-size, border-radius, and color scheme.",
     "tags": "button style padding font-size border-radius consistency"},
    {"id": "ui_spacing",         "category": "ui_consistency", "severity": "low",
     "rule": "Use a consistent spacing system (e.g. 4px/8px/12px/16px/24px grid). Avoid arbitrary margin/padding values.",
     "tags": "margin padding spacing grid system gap css"},
    {"id": "ui_color_tokens",    "category": "ui_consistency", "severity": "medium",
     "rule": "Use CSS custom properties (variables) for colors instead of hardcoded hex/rgb values to maintain theme consistency.",
     "tags": "color hex rgb css variable custom property theme"},
    {"id": "ui_font_consistency","category": "ui_consistency", "severity": "low",
     "rule": "Use a consistent font family and size scale across the application. Avoid mixing too many different font sizes.",
     "tags": "font family size typography text style"},
    {"id": "ui_responsive",      "category": "ui_consistency", "severity": "medium",
     "rule": "Layouts should be responsive using flexbox/grid with media queries. Avoid fixed pixel widths for containers.",
     "tags": "responsive media query flexbox grid mobile width"},
    {"id": "ui_hover_focus",     "category": "ui_consistency", "severity": "low",
     "rule": "Interactive elements should have hover and focus states that provide visual feedback.",
     "tags": "hover focus state transition visual feedback interactive"},
    {"id": "ui_z_index",         "category": "ui_consistency", "severity": "low",
     "rule": "Use a z-index scale/system. Avoid arbitrary high z-index values (e.g. z-index: 99999).",
     "tags": "z-index stacking context layer css"},

    # ── UX Issues ──
    {"id": "ux_loading_state",   "category": "ux", "severity": "medium",
     "rule": "API calls and async operations should show loading indicators. Users must get feedback that something is happening.",
     "tags": "loading spinner async fetch api axios wait"},
    {"id": "ux_error_feedback",  "category": "ux", "severity": "high",
     "rule": "Failed API calls must show user-friendly error messages, not silent failures or raw error strings.",
     "tags": "error message feedback catch try api failure"},
    {"id": "ux_empty_state",     "category": "ux", "severity": "medium",
     "rule": "Lists and data views should handle empty states gracefully with helpful messages or call-to-action.",
     "tags": "empty state list no data placeholder v-if v-for"},
    {"id": "ux_form_validation", "category": "ux", "severity": "medium",
     "rule": "Forms should validate input and show inline error messages before submission. Don't rely only on server-side validation.",
     "tags": "form validation error message input required pattern"},
    {"id": "ux_confirm_delete",  "category": "ux", "severity": "high",
     "rule": "Destructive actions (delete, remove, clear) must have a confirmation dialog or undo option.",
     "tags": "delete remove confirm dialog destructive action modal"},
    {"id": "ux_nav_feedback",    "category": "ux", "severity": "low",
     "rule": "Navigation should clearly indicate the current active route/page with visual highlighting.",
     "tags": "navigation active route link menu sidebar highlight"},

    # ── Vue-specific ──
    {"id": "vue_v_for_key",      "category": "performance", "severity": "high",
     "rule": "v-for directives must have a :key binding using a unique identifier, not the array index.",
     "tags": "v-for key unique index vue list render"},
    {"id": "vue_v_html_xss",     "category": "security", "severity": "high",
     "rule": "v-html renders raw HTML and is vulnerable to XSS attacks. Never use v-html with user-supplied content.",
     "tags": "v-html xss security injection raw html vue"},
    {"id": "vue_prop_types",     "category": "code_quality", "severity": "medium",
     "rule": "Vue component props should have type definitions and validators. Avoid untyped props.",
     "tags": "props type validator required default vue component"},
    {"id": "vue_emit_naming",    "category": "code_quality", "severity": "low",
     "rule": "Vue event names emitted via $emit should use kebab-case and be declared in emits option.",
     "tags": "emit event kebab-case emits option vue"},
    {"id": "vue_computed",       "category": "performance", "severity": "medium",
     "rule": "Complex expressions in templates should be moved to computed properties for performance and readability.",
     "tags": "computed template expression complex method vue"},
    {"id": "vue_watcher_cleanup","category": "performance", "severity": "medium",
     "rule": "Watchers that set up side effects (intervals, event listeners) must clean up in beforeUnmount or use onScopeDispose.",
     "tags": "watch watcher cleanup unmount dispose interval event listener memory leak"},

    # ── Code Quality ──
    {"id": "cq_console_log",     "category": "code_quality", "severity": "low",
     "rule": "Remove console.log, console.debug, and console.warn statements from production code.",
     "tags": "console log debug warn production cleanup"},
    {"id": "cq_hardcoded_url",   "category": "code_quality", "severity": "medium",
     "rule": "API URLs and endpoints should not be hardcoded. Use environment variables or a config file.",
     "tags": "url endpoint hardcoded api http localhost env config"},
    {"id": "cq_dead_code",       "category": "code_quality", "severity": "low",
     "rule": "Remove unused variables, imports, and functions. Dead code increases maintenance burden.",
     "tags": "unused variable import function dead code"},
    {"id": "cq_error_handling",  "category": "code_quality", "severity": "high",
     "rule": "Async operations (fetch, axios, file I/O) must be wrapped in try-catch with proper error handling.",
     "tags": "try catch error handling async await fetch promise"},
    {"id": "cq_magic_numbers",   "category": "code_quality", "severity": "low",
     "rule": "Avoid magic numbers in code. Use named constants with clear intent.",
     "tags": "magic number constant named variable"},
    {"id": "cq_long_function",   "category": "code_quality", "severity": "medium",
     "rule": "Functions longer than ~50 lines should be broken down into smaller, focused helper functions.",
     "tags": "function method long complex refactor extract"},
    {"id": "cq_todo_fixme",      "category": "code_quality", "severity": "low",
     "rule": "TODO and FIXME comments indicate unfinished work. Track these and resolve before release.",
     "tags": "todo fixme hack comment unfinished"},

    # ── Security ──
    {"id": "sec_hardcoded_secret","category": "security", "severity": "high",
     "rule": "Never hardcode API keys, passwords, tokens, or secrets in source code. Use environment variables.",
     "tags": "api key password token secret hardcoded env"},
    {"id": "sec_eval",           "category": "security", "severity": "high",
     "rule": "Never use eval(), new Function(), or setTimeout/setInterval with string arguments. These enable code injection.",
     "tags": "eval function setTimeout setInterval injection security"},
    {"id": "sec_inner_html",     "category": "security", "severity": "high",
     "rule": "Avoid innerHTML with user-supplied data. Use textContent or sanitize HTML before insertion.",
     "tags": "innerHTML innerhtml xss sanitize textContent security"},
    {"id": "sec_open_redirect",  "category": "security", "severity": "medium",
     "rule": "Validate URLs before using them in window.location or <a> tags to prevent open redirect vulnerabilities.",
     "tags": "window location redirect url href open redirect"},

    # ── Performance ──
    {"id": "perf_lazy_load",     "category": "performance", "severity": "low",
     "rule": "Large components and route views should use lazy loading (dynamic import) to reduce initial bundle size.",
     "tags": "lazy load dynamic import async component route bundle"},
    {"id": "perf_large_list",    "category": "performance", "severity": "medium",
     "rule": "Large lists (100+ items) should use virtual scrolling instead of rendering all items in the DOM.",
     "tags": "list virtual scroll large dom performance v-for"},
    {"id": "perf_inline_style",  "category": "performance", "severity": "low",
     "rule": "Avoid large inline style objects in templates. Move them to CSS classes or computed properties.",
     "tags": "inline style object template css class computed"},
    {"id": "perf_debounce",      "category": "performance", "severity": "medium",
     "rule": "Event handlers for frequent events (scroll, resize, input) should be debounced or throttled.",
     "tags": "debounce throttle scroll resize input event handler performance"},

    # ── CSS-specific ──
    {"id": "css_important",      "category": "code_quality", "severity": "low",
     "rule": "Avoid !important in CSS. It breaks the cascade and makes styles hard to override. Use more specific selectors instead.",
     "tags": "important css specificity cascade override selector"},
    {"id": "css_vendor_prefix",  "category": "code_quality", "severity": "low",
     "rule": "Use autoprefixer or PostCSS instead of manually adding -webkit-, -moz- vendor prefixes.",
     "tags": "vendor prefix webkit moz css autoprefixer"},
]


# ─────────────────────────────────────────────
# ChromaDB Knowledge Store
# ─────────────────────────────────────────────
CHROMA_DIR = os.path.join(os.path.dirname(__file__), '.chroma_db')
COLLECTION_NAME = "uiux_rules"


def _init_chromadb():
    """Initialize ChromaDB and populate the rules collection."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Check if collection already populated
    try:
        collection = client.get_collection(COLLECTION_NAME)
        if collection.count() == len(KNOWLEDGE_BASE):
            print(f"   [ChromaDB] Knowledge base loaded ({collection.count()} rules)")
            return client, collection
        # Rules changed, recreate
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    # Create and populate
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "UI/UX analysis rules and best practices"}
    )

    ids = [r["id"] for r in KNOWLEDGE_BASE]
    documents = [f"{r['rule']} Tags: {r['tags']}" for r in KNOWLEDGE_BASE]
    metadatas = [{"category": r["category"], "severity": r["severity"], "rule": r["rule"]}
                 for r in KNOWLEDGE_BASE]

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    print(f"   [ChromaDB] Knowledge base created with {len(KNOWLEDGE_BASE)} rules")
    return client, collection


# ─────────────────────────────────────────────
# RAG: Retrieve relevant rules for a code file
# ─────────────────────────────────────────────
def retrieve_relevant_rules(collection, code: str, file_ext: str, top_k: int = 15) -> list:
    """
    Query ChromaDB with the code content to find the most relevant rules.
    Returns a list of rule dicts with relevance scores.
    """
    # Build a query that captures the essence of the code
    # Use a combination of the code and file type hints
    query_text = f"File type: {file_ext}\n{code[:3000]}"

    results = collection.query(
        query_texts=[query_text],
        n_results=min(top_k, len(KNOWLEDGE_BASE)),
        include=["documents", "metadatas", "distances"]
    )

    rules = []
    if results and results['metadatas'] and results['metadatas'][0]:
        for i, meta in enumerate(results['metadatas'][0]):
            rules.append({
                'id': results['ids'][0][i],
                'rule': meta['rule'],
                'category': meta['category'],
                'severity': meta['severity'],
                'relevance': 1.0 - (results['distances'][0][i] if results['distances'] else 0)
            })

    return rules


# ─────────────────────────────────────────────
# Gemini call with RAG context
# ─────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_DELAY = 3

RAG_PROMPT_TEMPLATE = """You are a senior frontend code auditor. You have been given a set of
RELEVANT RULES retrieved from a knowledge base, plus the source code to analyze.

Your job: check the code against EACH retrieved rule and report ALL violations.

FILE: {file_name} (extension: {ext})

═══ RETRIEVED RULES (from knowledge base) ═══
{rules_text}
═══ END RULES ═══

═══ SOURCE CODE ═══
{code}
═══ END CODE ═══

INSTRUCTIONS:
1. Check the code against EVERY rule listed above.
2. For each violation found, create an issue object.
3. Be thorough — check every line of code against every relevant rule.
4. Give accurate 1-based line numbers.
5. Provide a concrete fix for each issue.

For EACH issue, return a JSON object with these exact fields:
- "rule_id": the ID from the retrieved rule (e.g. "a11y_img_alt")
- "category": one of "accessibility", "ui_consistency", "ux", "code_quality", "security", "performance"
- "severity": one of "high", "medium", "low"
- "message": short one-line issue title
- "description": clear explanation of what is wrong and WHY
- "line": the 1-based line number (integer)
- "fix": object with "description" (string), "original" (exact code from source), "replacement" (corrected code)

Return: {{"issues": [...]}}
If no violations: {{"issues": []}}

IMPORTANT: The "original" in fix MUST exactly match text in the source. Be precise with line numbers.
"""


def _call_gemini_rag(file_name: str, ext: str, code: str, rules: list) -> list:
    """Send code + retrieved rules to Gemini for analysis."""

    max_chars = 25000
    if len(code) > max_chars:
        code = code[:max_chars] + "\n\n... [TRUNCATED] ..."

    # Format retrieved rules
    rules_text = ""
    for i, r in enumerate(rules, 1):
        rules_text += f"{i}. [{r['id']}] ({r['category']} | {r['severity']}) — {r['rule']}\n"

    prompt = RAG_PROMPT_TEMPLATE.format(
        file_name=file_name, ext=ext, code=code, rules_text=rules_text
    )

    for attempt in range(MAX_RETRIES):
        try:
            response = _model.generate_content(prompt)
            text = response.text.strip()
            data = json.loads(text)
            issues = data.get("issues", [])

            valid = []
            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                if "message" not in issue and "rule_id" not in issue:
                    continue
                issue.setdefault("rule_id", "llm_detected")
                issue.setdefault("category", "code_quality")
                issue.setdefault("severity", "medium")
                issue.setdefault("message", issue.get("rule_id", "Issue detected"))
                issue.setdefault("description", "")
                issue.setdefault("line", 0)
                issue["severity"] = issue["severity"].lower()
                if issue["severity"] not in ("high", "medium", "low"):
                    issue["severity"] = "medium"

                fix = issue.get("fix")
                if fix and isinstance(fix, dict):
                    fix.setdefault("description", "Apply suggested fix")
                    fix.setdefault("original", "")
                    fix.setdefault("replacement", "")
                    if not fix["original"]:
                        issue["fix"] = None
                else:
                    issue["fix"] = None

                valid.append(issue)
            return valid

        except json.JSONDecodeError:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            print(f" [WARN] Could not parse Gemini response for {file_name}")
            return []
        except Exception as e:
            err_str = str(e)
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (attempt + 1)
                if "429" in err_str or "Quota" in err_str:
                    wait = 15
                    print(f"\n      [RATE LIMIT] Waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f" [WARN] Gemini error for {file_name}: {e}")
            return []


# ─────────────────────────────────────────────
# Public API — RAGScannerEngine
# ─────────────────────────────────────────────
SCANNABLE_EXTENSIONS = {'.vue', '.html', '.htm', '.css', '.scss', '.js', '.ts', '.jsx', '.tsx'}
DEFAULT_EXCLUDES = {'node_modules', 'dist', 'build', '.nuxt', '.output', '.git', '.vscode',
                    '__pycache__', '.cache', 'coverage', '.nyc_output', 'vendor'}


class RAGScannerEngine:
    """ChromaDB RAG-powered scanner using Gemini for code analysis."""

    def __init__(self, max_file_size_kb=500):
        self.max_file_size_kb = max_file_size_kb
        self._scan_cache = {}
        self._chroma_client = None
        self._collection = None
        self._init_knowledge_base()

    def _init_knowledge_base(self):
        """Initialize ChromaDB with the UI/UX rules knowledge base."""
        self._chroma_client, self._collection = _init_chromadb()

    def discover_files(self, project_path: str) -> list:
        files = []
        if os.path.isfile(project_path):
            ext = os.path.splitext(project_path)[1].lower()
            if ext in SCANNABLE_EXTENSIONS:
                return [os.path.abspath(project_path)]
            return []

        for root, dirs, filenames in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDES and not d.startswith('.')]
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext in SCANNABLE_EXTENSIONS:
                    filepath = os.path.join(root, filename)
                    try:
                        if os.path.getsize(filepath) / 1024 <= self.max_file_size_kb:
                            files.append(os.path.abspath(filepath))
                    except OSError:
                        continue
        return sorted(files)

    def scan_file(self, file_path: str, force: bool = False) -> list:
        file_path = os.path.abspath(file_path)
        if not force and file_path in self._scan_cache:
            return self._scan_cache[file_path]

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except (IOError, OSError):
            return []

        if not content.strip():
            return []

        file_name = os.path.basename(file_path)
        ext = os.path.splitext(file_name)[1].lstrip('.')

        # ── RAG Step 1: Retrieve relevant rules from ChromaDB ──
        relevant_rules = retrieve_relevant_rules(self._collection, content, ext)
        rule_ids = [r['id'] for r in relevant_rules[:10]]
        print(f"   [RAG] {file_name}: retrieved {len(relevant_rules)} rules → {rule_ids[:5]}...", end="", flush=True)

        # ── RAG Step 2: Send code + rules to Gemini ──
        issues = _call_gemini_rag(file_name, ext, content, relevant_rules)

        for issue in issues:
            issue['file'] = file_path

        print(f" → {len(issues)} issues")
        self._scan_cache[file_path] = issues
        return issues

    def scan_project(self, project_path: str, force: bool = False, max_files: int = 10) -> dict:
        start_time = time.time()
        project_path = os.path.abspath(project_path)
        all_files = self.discover_files(project_path)

        # Prioritize .vue files, then limit to max_files
        vue_files = [f for f in all_files if f.endswith('.vue')]
        other_files = [f for f in all_files if not f.endswith('.vue')]
        files = (vue_files + other_files)[:max_files]

        print(f"\n   [RAG Scanner] Found {len(all_files)} total files, scanning {len(files)} (max={max_files})")
        print(f"   ChromaDB: {self._collection.count()} rules | Model: {MODEL_NAME}")

        all_issues = []
        files_scanned = []
        consecutive_errors = 0

        for idx, file_path in enumerate(files, 1):
            print(f"   [{idx}/{len(files)}]", end=" ")
            try:
                issues = self.scan_file(file_path, force=force)
                all_issues.extend(issues)
                files_scanned.append(file_path)
                consecutive_errors = 0
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Quota" in err_str:
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        print(f"\n   [RAG] STOPPING — API quota exhausted")
                        break
                else:
                    print(f"   FAILED: {err_str[:60]}")

            if idx < len(files):
                time.sleep(4)

        scan_duration = time.time() - start_time
        result = {
            'timestamp': time.time(),
            'project_path': project_path,
            'issues': all_issues,
            'file_count': len(files_scanned),
            'scan_duration': round(scan_duration, 2),
            'files_scanned': files_scanned,
            'scanner': 'chromadb-rag',
            'model': MODEL_NAME,
            'knowledge_base_size': self._collection.count(),
            'summary': {
                'total': len(all_issues),
                'high': sum(1 for i in all_issues if i.get('severity') == 'high'),
                'medium': sum(1 for i in all_issues if i.get('severity') == 'medium'),
                'low': sum(1 for i in all_issues if i.get('severity') == 'low'),
                'by_category': self._group_by(all_issues, 'category'),
                'by_file': self._group_by(all_issues, 'file'),
            }
        }

        print(f"\n   [RAG Scanner] Done in {result['scan_duration']}s")
        print(f"   Files: {result['file_count']} | Issues: {result['summary']['total']} "
              f"(H:{result['summary']['high']} M:{result['summary']['medium']} L:{result['summary']['low']})")
        return result

    @staticmethod
    def _group_by(issues, key):
        groups = {}
        for i in issues:
            v = i.get(key, 'other')
            groups[v] = groups.get(v, 0) + 1
        return groups
