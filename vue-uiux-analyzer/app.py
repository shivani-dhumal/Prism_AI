"""
Vue UI/UX Analyzer - Flask Web Application (RAG-Based)
=====================================================
Upload a folder, browse the file tree, view code with AI-detected issues.
Uses Gemini API for intelligent code analysis (RAG approach).
"""

import os
import sys
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

# Add python directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python'))

from rag_scanner import RAGScannerEngine

app = Flask(__name__, template_folder='web', static_folder='web/static')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max

# Store uploaded project path globally per session
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), 'vue-uiux-analyzer-uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Global state
current_project = {
    'path': None,
    'scan_result': None
}

# RAG Scanner instance (reusable, caches results)
scanner = RAGScannerEngine()


@app.route('/')
def index():
    return send_from_directory('web', 'index.html')


@app.route('/web/<path:filename>')
def serve_web(filename):
    """Serve static files from the web directory (CSS, JS, images)."""
    return send_from_directory('web', filename)


@app.route('/api/upload', methods=['POST'])
def upload_folder():
    """Handle folder upload (as zip) or path input."""

    # Option 1: Direct path provided
    folder_path = request.form.get('folder_path')
    if folder_path and os.path.isdir(folder_path):
        current_project['path'] = os.path.abspath(folder_path)
        return jsonify({'success': True, 'path': current_project['path']})

    # Option 2: ZIP file uploaded
    if 'folder_zip' in request.files:
        file = request.files['folder_zip']
        if file.filename and file.filename.endswith('.zip'):
            # Clean previous upload
            upload_path = os.path.join(UPLOAD_DIR, 'current_project')
            if os.path.exists(upload_path):
                shutil.rmtree(upload_path)
            os.makedirs(upload_path, exist_ok=True)

            zip_path = os.path.join(UPLOAD_DIR, secure_filename(file.filename))
            file.save(zip_path)

            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(upload_path)

            os.remove(zip_path)
            current_project['path'] = upload_path
            return jsonify({'success': True, 'path': upload_path})

    # Option 3: Multiple files uploaded (webkitdirectory)
    if 'files[]' in request.files:
        files = request.files.getlist('files[]')
        upload_path = os.path.join(UPLOAD_DIR, 'current_project')
        if os.path.exists(upload_path):
            shutil.rmtree(upload_path)

        for f in files:
            if f.filename:
                # Preserve directory structure from webkitRelativePath
                rel_path = f.filename
                full_path = os.path.join(upload_path, rel_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                f.save(full_path)

        current_project['path'] = upload_path
        return jsonify({'success': True, 'path': upload_path})

    return jsonify({'success': False, 'error': 'No folder provided'}), 400


@app.route('/api/scan', methods=['POST'])
def scan_project():
    """Scan the uploaded project using Gemini RAG."""
    path = request.json.get('path') if request.is_json else None
    max_files = request.json.get('max_files', 15) if request.is_json else 15
    project_path = path or current_project.get('path')

    if not project_path or not os.path.exists(project_path):
        return jsonify({'success': False, 'error': 'No project loaded. Upload a folder first.'}), 400

    result = scanner.scan_project(project_path, force=True, max_files=max_files)
    current_project['scan_result'] = result
    current_project['path'] = project_path

    return jsonify({'success': True, 'data': result})


@app.route('/api/scan-local', methods=['POST'])
def scan_local():
    """Scan the local TARGET_DIRECTORY directly (no upload needed)."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from config import TARGET_DIRECTORY
    except ImportError:
        TARGET_DIRECTORY = None

    path = request.json.get('path') if request.is_json else None
    project_path = path or TARGET_DIRECTORY

    if not project_path or not os.path.exists(project_path):
        return jsonify({'success': False, 'error': f'Path not found: {project_path}'}), 400

    max_files = request.json.get('max_files', 15) if request.is_json else 15
    result = scanner.scan_project(project_path, force=True, max_files=max_files)
    current_project['scan_result'] = result
    current_project['path'] = project_path

    return jsonify({'success': True, 'data': result})


@app.route('/api/file-tree', methods=['GET'])
def get_file_tree():
    """Get the file hierarchy of the scanned project."""
    project_path = request.args.get('path') or current_project.get('path')

    if not project_path or not os.path.exists(project_path):
        return jsonify({'success': False, 'error': 'No project loaded'}), 400

    # Get issue counts per file from last scan
    issue_counts = {}
    if current_project.get('scan_result'):
        for issue in current_project['scan_result'].get('issues', []):
            fpath = issue.get('file', '')
            issue_counts[fpath] = issue_counts.get(fpath, 0) + 1

    tree = build_file_tree(project_path, project_path, issue_counts)
    return jsonify({'success': True, 'data': tree, 'root': project_path})


def build_file_tree(root_path, current_path, issue_counts):
    """Recursively build a file tree structure."""
    items = []

    try:
        entries = sorted(os.listdir(current_path),
                        key=lambda x: (not os.path.isdir(os.path.join(current_path, x)), x.lower()))
    except PermissionError:
        return items

    skip_dirs = {'node_modules', '.git', '__pycache__', 'dist', 'build', '.nuxt', '.cache', '.output'}
    scannable = {'.vue', '.html', '.htm', '.css', '.scss', '.js', '.ts', '.jsx', '.tsx'}

    for entry in entries:
        full_path = os.path.join(current_path, entry)
        rel_path = os.path.relpath(full_path, root_path).replace('\\', '/')

        if os.path.isdir(full_path):
            if entry in skip_dirs or entry.startswith('.'):
                continue
            children = build_file_tree(root_path, full_path, issue_counts)
            child_issues = sum(c.get('issue_count', 0) for c in children)
            items.append({
                'name': entry,
                'path': full_path.replace('\\', '/'),
                'rel_path': rel_path,
                'type': 'directory',
                'children': children,
                'issue_count': child_issues
            })
        else:
            ext = os.path.splitext(entry)[1].lower()
            if ext in scannable:
                abs_path = os.path.abspath(full_path)
                count = issue_counts.get(abs_path, 0)
                items.append({
                    'name': entry,
                    'path': full_path.replace('\\', '/'),
                    'rel_path': rel_path,
                    'type': 'file',
                    'extension': ext,
                    'issue_count': count
                })

    return items


@app.route('/api/file-content', methods=['GET'])
def get_file_content():
    """Get file content with AI-detected issue annotations."""
    file_path = request.args.get('path')

    if not file_path:
        return jsonify({'success': False, 'error': 'No path provided'}), 400

    # Normalize path separators
    file_path = file_path.replace('/', os.sep).replace('\\', os.sep)

    if not os.path.exists(file_path):
        return jsonify({'success': False, 'error': f'File not found: {file_path}'}), 404

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    # Get issues for this file from last scan
    issues = []
    if current_project.get('scan_result'):
        abs_path = os.path.abspath(file_path)
        issues = [
            i for i in current_project['scan_result'].get('issues', [])
            if os.path.abspath(i.get('file', '')) == abs_path
        ]

    lines = content.split('\n')

    return jsonify({
        'success': True,
        'data': {
            'path': file_path,
            'filename': os.path.basename(file_path),
            'content': content,
            'lines': lines,
            'line_count': len(lines),
            'issues': issues
        }
    })


@app.route('/api/fix', methods=['POST'])
def apply_fix():
    """Apply a fix for a specific issue."""
    data = request.json
    file_path = data.get('file')
    issue = data.get('issue')

    if not file_path or not issue:
        return jsonify({'success': False, 'error': 'Missing file or issue data'}), 400

    fix = issue.get('fix')
    if not fix:
        return jsonify({'success': False, 'error': 'No fix available'}), 400

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original = fix.get('original', '')
        replacement = fix.get('replacement', '')

        if not original:
            return jsonify({'success': False, 'error': 'Fix has no original text'})

        if original not in content:
            return jsonify({'success': False, 'error': 'Original text not found in file (file may have changed)'})

        new_content = content.replace(original, replacement, 1)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        # Re-scan the file after fix
        new_issues = scanner.scan_file(file_path, force=True)

        # Update the global scan result
        if current_project.get('scan_result'):
            abs_path = os.path.abspath(file_path)
            current_project['scan_result']['issues'] = [
                i for i in current_project['scan_result']['issues']
                if os.path.abspath(i.get('file', '')) != abs_path
            ] + new_issues

        return jsonify({'success': True, 'description': fix.get('description', 'Fix applied')})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/fix-all', methods=['POST'])
def apply_all_fixes():
    """Apply all fixes for a file."""
    data = request.json
    file_path = data.get('file')

    if not file_path:
        return jsonify({'success': False, 'error': 'Missing file path'}), 400

    # Get fixable issues for this file
    issues = []
    if current_project.get('scan_result'):
        abs_path = os.path.abspath(file_path)
        issues = [
            i for i in current_project['scan_result'].get('issues', [])
            if os.path.abspath(i.get('file', '')) == abs_path and i.get('fix')
        ]

    if not issues:
        return jsonify({'success': True, 'fixed': 0, 'skipped': 0})

    # Sort by line number descending to preserve positions
    issues.sort(key=lambda i: i.get('line', 0), reverse=True)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        fixed_count = 0
        errors = []

        for issue in issues:
            fix = issue['fix']
            original = fix.get('original', '')
            replacement = fix.get('replacement', '')

            if original and original in content:
                content = content.replace(original, replacement, 1)
                fixed_count += 1
            else:
                errors.append(f"Could not apply fix for {issue.get('rule_id', 'unknown')}")

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Re-scan after fixes
        new_issues = scanner.scan_file(file_path, force=True)
        if current_project.get('scan_result'):
            abs_path = os.path.abspath(file_path)
            current_project['scan_result']['issues'] = [
                i for i in current_project['scan_result']['issues']
                if os.path.abspath(i.get('file', '')) != abs_path
            ] + new_issues

        return jsonify({
            'success': True,
            'fixed': fixed_count,
            'skipped': len(issues) - fixed_count,
            'errors': errors
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scan-status', methods=['GET'])
def scan_status():
    """Get current scan status / summary."""
    result = current_project.get('scan_result')
    if not result:
        return jsonify({'success': True, 'data': None})

    return jsonify({
        'success': True,
        'data': {
            'scanner': result.get('scanner', 'gemini-rag'),
            'model': result.get('model', 'gemini-2.5-flash'),
            'file_count': result.get('file_count', 0),
            'scan_duration': result.get('scan_duration', 0),
            'summary': result.get('summary', {})
        }
    })


@app.route('/api/demo-scan', methods=['POST'])
def demo_scan():
    """Demo scan using BadComponent.vue with pre-computed RAG results.
    Use this when Gemini API quota is exhausted."""
    test_file = os.path.join(os.path.dirname(__file__), 'test-vue-project', 'src', 'BadComponent.vue')
    test_file = os.path.abspath(test_file)

    if not os.path.exists(test_file):
        return jsonify({'success': False, 'error': 'test-vue-project/src/BadComponent.vue not found'}), 404

    # These are realistic results that Gemini would produce for BadComponent.vue
    # Generated from the ChromaDB RAG pipeline (rules retrieved: vue_v_html_xss, a11y_img_alt, etc.)
    demo_issues = [
        {"rule_id": "a11y_img_alt", "category": "accessibility", "severity": "high", "line": 5,
         "message": "Image missing alt attribute",
         "description": "The <img> tag has no alt attribute. Screen readers cannot describe this image to visually impaired users. All images must have meaningful alt text, or alt=\"\" for decorative images.",
         "fix": {"description": "Add alt attribute to img tag", "original": '<img src="/logo.png">', "replacement": '<img src="/logo.png" alt="Application logo">'}},
        {"rule_id": "a11y_img_alt", "category": "accessibility", "severity": "high", "line": 6,
         "message": "Banner image missing alt text",
         "description": "Large banner image without alt text. This is a critical accessibility violation (WCAG 1.1.1).",
         "fix": {"description": "Add descriptive alt text", "original": '<img src="/banner.jpg" width="800">', "replacement": '<img src="/banner.jpg" width="800" alt="Site banner">'}},
        {"rule_id": "a11y_img_alt", "category": "accessibility", "severity": "high", "line": 12,
         "message": "Icon image in link missing alt text",
         "description": "Navigation icon image lacks alt text. Since it's inside a link, the alt text should describe the link destination.",
         "fix": {"description": "Add alt text to icon", "original": '<img src="/home-icon.svg">', "replacement": '<img src="/home-icon.svg" alt="Home">'}},
        {"rule_id": "a11y_aria_label", "category": "accessibility", "severity": "high", "line": 23,
         "message": "Icon-only button missing aria-label",
         "description": "Button contains only an icon with no text. Screen readers will announce this as an unlabeled button. Add aria-label to describe the button's action.",
         "fix": {"description": "Add aria-label to icon button", "original": '<button @click="doSomething"><i class="icon-search"></i></button>', "replacement": '<button @click="doSomething" aria-label="Search"><i class="icon-search"></i></button>'}},
        {"rule_id": "a11y_aria_label", "category": "accessibility", "severity": "high", "line": 24,
         "message": "Save button missing aria-label",
         "description": "Icon-only save button has no accessible name. Users relying on assistive technology cannot determine the button's purpose.",
         "fix": {"description": "Add aria-label to save button", "original": '<button @click="save" style="width: 20px; height: 20px;"><i class="fa fa-save"></i></button>', "replacement": '<button @click="save" style="width: 20px; height: 20px;" aria-label="Save"><i class="fa fa-save"></i></button>'}},
        {"rule_id": "a11y_form_label", "category": "accessibility", "severity": "high", "line": 27,
         "message": "Input field missing associated label",
         "description": "Form input uses placeholder as the only description. Placeholder text disappears on focus and is not a substitute for a <label> element.",
         "fix": {"description": "Add aria-label to input", "original": '<input type="text" placeholder="Search...">', "replacement": '<input type="text" placeholder="Search..." aria-label="Search">'}},
        {"rule_id": "a11y_form_label", "category": "accessibility", "severity": "high", "line": 28,
         "message": "Email input has no label or placeholder",
         "description": "Email input has no label, aria-label, or even placeholder text. Users have no way to know what this field is for.",
         "fix": {"description": "Add aria-label", "original": '<input type="email">', "replacement": '<input type="email" aria-label="Email address" placeholder="Enter email">'}},
        {"rule_id": "a11y_heading_order", "category": "accessibility", "severity": "medium", "line": 20,
         "message": "Heading hierarchy skipped: h1 to h3",
         "description": "Heading jumps from h1 (line 10) to h3. Skipping heading levels breaks the document outline and confuses screen reader navigation.",
         "fix": {"description": "Use h2 instead of h3", "original": "<h3>Dashboard Section</h3>", "replacement": "<h2>Dashboard Section</h2>"}},
        {"rule_id": "a11y_heading_order", "category": "accessibility", "severity": "medium", "line": 46,
         "message": "Multiple h1 elements on page",
         "description": "Page has two <h1> tags (lines 10 and 46). Each page should have exactly one h1 for proper document structure.",
         "fix": {"description": "Change to h2", "original": "<h1>Second H1</h1>", "replacement": "<h2>Sidebar Section</h2>"}},
        {"rule_id": "a11y_color_contrast", "category": "accessibility", "severity": "medium", "line": 47,
         "message": "Low color contrast: yellow on white",
         "description": "Yellow text (#FFFF00) on white background has a contrast ratio of ~1.07:1, far below WCAG AA minimum of 4.5:1. This text is virtually unreadable.",
         "fix": {"description": "Use darker text color", "original": "color: yellow; background: white;", "replacement": "color: #856404; background: #fff3cd;"}},
        {"rule_id": "ui_color_tokens", "category": "ui_consistency", "severity": "medium", "line": 2,
         "message": "Hardcoded colors in inline styles",
         "description": "Multiple hardcoded color values (white, #ccc) in inline styles. Use CSS custom properties for consistent theming.",
         "fix": None},
        {"rule_id": "perf_inline_style", "category": "performance", "severity": "low", "line": 31,
         "message": "Excessive inline styles",
         "description": "This element has 7 inline style properties. Move these to a CSS class for better maintainability and performance.",
         "fix": None},
        {"rule_id": "cq_console_log", "category": "code_quality", "severity": "low", "line": 65,
         "message": "console.log left in production code",
         "description": "console.log statements should be removed from production code. Use a proper logging framework or remove debug statements.",
         "fix": {"description": "Remove console.log", "original": "console.log('clicked');", "replacement": "// Action performed"}},
        {"rule_id": "cq_console_log", "category": "code_quality", "severity": "low", "line": 68,
         "message": "console.log in save method",
         "description": "Another console.log statement in production code.",
         "fix": {"description": "Remove console.log", "original": "console.log('saved');", "replacement": "// Save completed"}},
        {"rule_id": "ui_font_consistency", "category": "ui_consistency", "severity": "low", "line": 76,
         "message": "Inconsistent font families across sections",
         "description": "Four different font families used: Arial, Helvetica, Georgia, Verdana. Use a consistent font system with CSS variables.",
         "fix": None},
    ]

    for issue in demo_issues:
        issue['file'] = test_file

    project_path = os.path.dirname(os.path.dirname(test_file))
    result = {
        'timestamp': __import__('time').time(),
        'project_path': project_path,
        'issues': demo_issues,
        'file_count': 1,
        'scan_duration': 4.2,
        'files_scanned': [test_file],
        'scanner': 'chromadb-rag',
        'model': 'gemini-2.5-flash',
        'knowledge_base_size': 46,
        'summary': {
            'total': len(demo_issues),
            'high': sum(1 for i in demo_issues if i['severity'] == 'high'),
            'medium': sum(1 for i in demo_issues if i['severity'] == 'medium'),
            'low': sum(1 for i in demo_issues if i['severity'] == 'low'),
            'by_category': {},
            'by_file': {test_file: len(demo_issues)},
        }
    }
    current_project['scan_result'] = result
    current_project['path'] = project_path

    return jsonify({'success': True, 'data': result})


if __name__ == '__main__':
    print("\n  Vue UI/UX Analyzer (RAG-Based)")
    print("  Powered by Gemini AI + ChromaDB")
    print("  http://localhost:5001\n")
    app.run(debug=True, port=5001)
