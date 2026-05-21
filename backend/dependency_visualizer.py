#!/usr/bin/env python3
"""
Interactive Dependency Visualizer
Generates an interactive HTML visualization of project dependencies
with zoom, pan, and focus capabilities.
"""

import os
import sys
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set, List

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

class DependencyVisualizer:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.dependencies: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_dependencies: Dict[str, Set[str]] = defaultdict(set)
        self.file_types = {'.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.go', '.java'}
        self.ignore_dirs = {
            '__pycache__', '.git', 'node_modules', '.venv', 'venv',
            '.env', '.pytest_cache', '.vscode', 'dist', 'build'
        }

    def analyze(self):
        """Scan and extract dependencies"""
        print("Analyzing dependencies...")
        for file_path in self._get_files():
            self._extract_dependencies(file_path)
        print(f"Found {len(self.dependencies)} files with dependencies")

    def _get_files(self) -> List[Path]:
        files = []
        for root, dirs, filenames in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            for filename in filenames:
                if any(filename.endswith(ext) for ext in self.file_types):
                    files.append(Path(root) / filename)
        return files

    def _extract_dependencies(self, file_path: Path):
        rel_path = str(file_path.relative_to(self.root_path)).replace('\\', '/')
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            imports = self._get_imports(content, file_path.suffix)
            for imp in imports:
                dep_path = self._resolve_import(imp, file_path)
                if dep_path and dep_path != rel_path:
                    self.dependencies[rel_path].add(dep_path)
                    self.reverse_dependencies[dep_path].add(rel_path)
        except:
            pass

    def _get_imports(self, content: str, ext: str) -> Set[str]:
        imports = set()
        if ext == '.py':
            for pattern in [r'from\s+([\w.]+)\s+import', r'import\s+([\w.]+)']:
                imports.update(m.split('.')[0] for m in re.findall(pattern, content))
        elif ext in {'.js', '.ts', '.jsx', '.tsx', '.vue'}:
            for pattern in [r'from\s+["\']([^"\']+)["\']', r'require\s*\(\s*["\']([^"\']+)["\']\s*\)']:
                imports.update(re.findall(pattern, content))
        elif ext == '.go':
            imports.update(re.findall(r'import\s+["\']([^"\']+)["\']', content))
        return imports

    def _resolve_import(self, imp: str, from_file: Path) -> str:
        candidates = [
            from_file.parent / f"{imp}.py",
            from_file.parent / imp / "__init__.py",
            self.root_path / f"{imp}.py",
            self.root_path / imp / "__init__.py",
            from_file.parent / f"{imp}.js",
            from_file.parent / f"{imp}.vue",
            from_file.parent / f"{imp}.ts",
        ]
        for c in candidates:
            if c.exists():
                return str(c.relative_to(self.root_path)).replace('\\', '/')
        return None

    def generate_html(self, output_file: str = "DEPENDENCY_GRAPH.html"):
        """Generate interactive HTML visualization"""
        nodes, edges = self._build_graph_data()
        data = nodes + edges
        data_json = json.dumps(data)

        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dependency Graph Visualizer</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.20.0/cytoscape.min.js"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-tertiary: #f8fafc;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --border-color: #e2e8f0;
            --canvas-bg: linear-gradient(135deg, #1e293b 0%, #0f172a 50%, #1a1f2e 100%);
            --card-bg: #ffffff;
            --header-bg: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}

        body.light-mode {{
            --bg-primary: #f8fafc;
            --bg-secondary: #ffffff;
            --bg-tertiary: #1e293b;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --border-color: #e2e8f0;
            --canvas-bg: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            --card-bg: #ffffff;
            --header-bg: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}

        body.light-mode #panel {{
            background: #ffffff;
            box-shadow: -8px 0 24px rgba(0,0,0,0.08);
        }}

        body.light-mode h2 {{
            color: #667eea;
        }}

        body.light-mode .focused-node {{
            background: linear-gradient(135deg, #f1f5f9, #e2e8f0);
            color: #0f172a;
        }}

        body.light-mode .item {{
            background: #f1f5f9;
            color: #1e293b;
        }}

        body.light-mode .item:hover {{
            background: #e2e8f0;
        }}

        body.light-mode .section-title {{
            color: #475569;
        }}

        body.light-mode .stat {{
            color: #475569;
            border-bottom-color: #e2e8f0;
        }}

        body.light-mode .metrics {{
            background: #f1f5f9;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--bg-primary); color: var(--text-primary); transition: background 0.3s, color 0.3s; }}

        #container {{ display: flex; height: 100vh; }}

        #canvas {{
            flex: 1;
            background: var(--canvas-bg);
            position: relative;
            overflow: hidden;
            transition: background 0.3s;
        }}

        .canvas-overlay {{
            position: absolute;
            top: 0; left: 0; right: 0;
            padding: 20px;
            background: linear-gradient(180deg, rgba(0,0,0,0.4), transparent);
            color: white;
            z-index: 10;
            pointer-events: none;
        }}

        .canvas-title {{
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 5px;
            background: linear-gradient(135deg, #60a5fa, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .canvas-subtitle {{
            font-size: 12px;
            opacity: 0.8;
        }}

        #panel {{
            width: 380px;
            background: var(--card-bg);
            border-left: 1px solid var(--border-color);
            overflow-y: auto;
            padding: 0;
            box-shadow: -8px 0 24px rgba(0,0,0,0.1);
            display: flex;
            flex-direction: column;
            transition: background 0.3s, border-color 0.3s;
        }}

        .panel-header {{
            background: var(--header-bg);
            color: white;
            padding: 25px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }}

        .panel-header-content {{ flex: 1; }}

        .panel-header h1 {{
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 12px;
        }}

        .controls {{
            display: flex;
            gap: 8px;
        }}

        input {{
            flex: 1;
            padding: 10px 14px;
            border: 1px solid rgba(255,255,255,0.3);
            border-radius: 8px;
            font-size: 13px;
            background: rgba(255,255,255,0.1);
            color: white;
            transition: all 0.3s;
        }}

        input::placeholder {{
            color: rgba(255,255,255,0.6);
        }}

        input:focus {{
            outline: none;
            background: rgba(255,255,255,0.2);
            border-color: rgba(255,255,255,0.5);
            box-shadow: 0 0 0 3px rgba(255,255,255,0.1);
        }}

        button {{
            padding: 10px 14px;
            background: rgba(255,255,255,0.2);
            color: white;
            border: 1px solid rgba(255,255,255,0.3);
            border-radius: 8px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 600;
            transition: all 0.3s;
        }}

        button:hover {{
            background: rgba(255,255,255,0.3);
            border-color: rgba(255,255,255,0.5);
            transform: translateY(-1px);
        }}

        #theme-toggle {{
            padding: 8px 12px;
            background: rgba(255,255,255,0.15);
            color: white;
            border: 1px solid rgba(255,255,255,0.25);
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
            margin-left: 10px;
        }}

        #theme-toggle:hover {{
            background: rgba(255,255,255,0.25);
        }}

        #info {{
            flex: 1;
            padding: 20px;
            overflow-y: auto;
        }}

        h2 {{
            color: #667eea;
            margin-bottom: 18px;
            font-size: 16px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        h2:before {{
            content: '';
            width: 3px;
            height: 20px;
            background: linear-gradient(180deg, #667eea, #764ba2);
            border-radius: 2px;
        }}

        .focused-node {{
            background: linear-gradient(135deg, #f8fafc, #f1f5f9);
            border: 2px solid #667eea;
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 16px;
            font-weight: 600;
            color: #0f172a;
        }}

        .section {{
            margin-bottom: 24px;
        }}

        .section-title {{
            color: #64748b;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .item {{
            padding: 10px 12px;
            margin: 6px 0;
            background: #f1f5f9;
            border-radius: 8px;
            font-size: 12px;
            border-left: 3px solid #667eea;
            transition: all 0.2s;
            cursor: pointer;
        }}

        .item:hover {{
            background: #e2e8f0;
            transform: translateX(4px);
        }}

        .stat {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            font-size: 13px;
            color: #475569;
            border-bottom: 1px solid #e2e8f0;
        }}

        .stat:last-child {{
            border-bottom: none;
        }}

        .stat-value {{
            font-weight: 700;
            color: #667eea;
            font-size: 16px;
        }}

        .metrics {{
            background: linear-gradient(135deg, #f8fafc, #f1f5f9);
            border-radius: 10px;
            padding: 14px;
            margin-top: 16px;
        }}

        ::-webkit-scrollbar {{
            width: 6px;
        }}

        ::-webkit-scrollbar-track {{
            background: #f1f5f9;
        }}

        ::-webkit-scrollbar-thumb {{
            background: #cbd5e1;
            border-radius: 3px;
        }}

        ::-webkit-scrollbar-thumb:hover {{
            background: #94a3b8;
        }}

        /* Mind Map Button */
        #mindmap-btn {{
            padding: 8px 14px;
            background: linear-gradient(135deg, #a78bfa, #7c3aed);
            color: white;
            border: 1px solid rgba(167,139,250,0.5);
            border-radius: 8px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 700;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 6px;
            white-space: nowrap;
            box-shadow: 0 2px 12px rgba(124,58,237,0.35);
        }}
        #mindmap-btn:hover {{
            background: linear-gradient(135deg, #c4b5fd, #8b5cf6);
            transform: translateY(-1px);
            box-shadow: 0 4px 20px rgba(124,58,237,0.5);
        }}

        /* Mind Map Modal */
        #mindmap-modal {{
            display: none;
            position: fixed;
            inset: 0;
            z-index: 9999;
            background: rgba(7,10,20,0.92);
            backdrop-filter: blur(12px);
            animation: mmFadeIn 0.3s ease;
        }}
        @keyframes mmFadeIn {{
            from {{ opacity: 0; transform: scale(0.97); }}
            to   {{ opacity: 1; transform: scale(1); }}
        }}
        #mindmap-modal.closing {{
            animation: mmFadeOut 0.25s ease forwards;
        }}
        @keyframes mmFadeOut {{
            from {{ opacity: 1; transform: scale(1); }}
            to   {{ opacity: 0; transform: scale(0.97); }}
        }}
        #mindmap-header {{
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 64px;
            background: linear-gradient(90deg, rgba(124,58,237,0.9), rgba(99,102,241,0.9));
            display: flex;
            align-items: center;
            padding: 0 24px;
            gap: 14px;
            z-index: 10;
            backdrop-filter: blur(8px);
            border-bottom: 1px solid rgba(167,139,250,0.3);
        }}
        #mindmap-header h2 {{
            color: white;
            font-size: 18px;
            font-weight: 700;
            margin: 0;
        }}
        #mindmap-header h2::before {{ display:none; }}
        #mindmap-subtitle {{
            color: rgba(255,255,255,0.65);
            font-size: 13px;
            flex: 1;
        }}
        #mindmap-layout-group {{
            display: flex;
            gap: 8px;
        }}
        .mm-layout-btn {{
            padding: 6px 14px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.25);
            background: rgba(255,255,255,0.1);
            color: rgba(255,255,255,0.8);
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .mm-layout-btn.active, .mm-layout-btn:hover {{
            background: rgba(255,255,255,0.25);
            color: white;
            border-color: rgba(255,255,255,0.5);
        }}
        #mindmap-close {{
            padding: 8px 12px;
            background: rgba(239,68,68,0.2);
            border: 1px solid rgba(239,68,68,0.4);
            border-radius: 8px;
            color: #fca5a5;
            font-size: 18px;
            cursor: pointer;
            transition: all 0.2s;
            line-height: 1;
        }}
        #mindmap-close:hover {{
            background: rgba(239,68,68,0.4);
            color: white;
        }}
        #mindmap-canvas {{
            position: absolute;
            top: 64px;
            left: 0; right: 0; bottom: 0;
        }}
        #mindmap-legend {{
            position: absolute;
            bottom: 20px;
            left: 20px;
            background: rgba(15,23,42,0.85);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 14px 18px;
            z-index: 10;
            backdrop-filter: blur(8px);
            min-width: 180px;
        }}
        #mindmap-legend .legend-title {{
            color: rgba(255,255,255,0.5);
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 7px;
            font-size: 12px;
            color: rgba(255,255,255,0.8);
        }}
        .legend-dot {{
            width: 12px; height: 12px;
            border-radius: 50%;
            flex-shrink: 0;
        }}
        #mindmap-tip {{
            position: absolute;
            bottom: 20px;
            right: 20px;
            background: rgba(15,23,42,0.7);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 10px 14px;
            color: rgba(255,255,255,0.4);
            font-size: 11px;
            z-index: 10;
        }}
    </style>
</head>
<body>
    <div id="container">
        <div id="canvas">
            <div class="canvas-overlay">
                <div class="canvas-title">Dependency Explorer</div>
                <div class="canvas-subtitle">Click any file to view dependencies</div>
            </div>
        </div>
        <div id="panel">
            <div class="panel-header">
                <div class="panel-header-content">
                    <h1>File Inspector</h1>
                    <div class="controls">
                        <input type="text" id="search" placeholder="Search files...">
                        <button id="reset" title="Reset view"><i class="fas fa-redo"></i></button>
                        <button id="mindmap-btn" title="Open Mind Map"><i class="fas fa-brain"></i> Mind Map</button>
                    </div>
                </div>
                <button id="theme-toggle" title="Toggle theme"><i class="fas fa-moon"></i></button>
            </div>
            <div id="info">
                <div style="text-align: center; padding: 40px 20px; color: #94a3b8;">
                    <i class="fas fa-mouse" style="font-size: 32px; margin-bottom: 12px;"></i>
                    <p>Click a file to explore</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Mind Map Modal -->
    <div id="mindmap-modal">
        <div id="mindmap-header">
            <span style="font-size:22px;">&#129504;</span>
            <h2>Dependency Mind Map</h2>
            <span id="mindmap-subtitle">Radial view of all module relationships</span>
            <div id="mindmap-layout-group">
                <button class="mm-layout-btn active" data-layout="concentric">Concentric</button>
                <button class="mm-layout-btn" data-layout="breadthfirst">Tree</button>
                <button class="mm-layout-btn" data-layout="cose">Force</button>
            </div>
            <button id="mindmap-close" title="Close (Esc)">&#x2715;</button>
        </div>
        <div id="mindmap-canvas"></div>
        <div id="mindmap-legend">
            <div class="legend-title">Module Groups</div>
            <div class="legend-item"><div class="legend-dot" style="background:#f59e0b;"></div>Root</div>
            <div class="legend-item"><div class="legend-dot" style="background:#10b981;"></div>Scanners</div>
            <div class="legend-item"><div class="legend-dot" style="background:#06b6d4;"></div>Code Analyzer</div>
            <div class="legend-item"><div class="legend-dot" style="background:#a78bfa;"></div>Vue UIux</div>
            <div class="legend-item"><div class="legend-dot" style="background:#f472b6;"></div>Gemini Chatbot</div>
            <div class="legend-item"><div class="legend-dot" style="background:#fb923c;"></div>VSCode Ext.</div>
        </div>
        <div id="mindmap-tip">&#x1F5B1; Drag to pan &nbsp;|&nbsp; Scroll to zoom &nbsp;|&nbsp; Click node to inspect</div>
    </div>

    <script>
        const data = __DATA_PLACEHOLDER__;
        const cy = cytoscape({{
            container: document.getElementById('canvas'),
            elements: data,
            style: [
                {{
                    selector: 'node',
                    style: {{
                        'content': 'data(label)',
                        'background-color': '#667eea',
                        'color': '#fff',
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'font-size': 11,
                        'font-weight': 'bold',
                        'padding': '12px',
                        'border-width': 2,
                        'border-color': '#764ba2',
                        'shadow-blur': 8,
                        'shadow-color': 'rgba(102, 126, 234, 0.4)',
                        'shadow-offset-x': 0,
                        'shadow-offset-y': 4
                    }}
                }},
                {{
                    selector: 'node.focused',
                    style: {{'background-color': '#f59e0b', 'border-width': 4, 'border-color': '#d97706', 'shadow-blur': 12, 'shadow-color': 'rgba(245, 158, 11, 0.5)'}}
                }},
                {{
                    selector: 'node.parent',
                    style: {{'background-color': '#10b981', 'border-color': '#059669'}}
                }},
                {{
                    selector: 'node.child',
                    style: {{'background-color': '#06b6d4', 'border-color': '#0891b2'}}
                }},
                {{
                    selector: 'edge',
                    style: {{
                        'target-arrow-shape': 'triangle',
                        'line-color': '#475569',
                        'target-arrow-color': '#475569',
                        'curve-style': 'bezier',
                        'width': 2,
                        'opacity': 0.6
                    }}
                }},
                {{
                    selector: 'edge.focused',
                    style: {{'line-color': '#f59e0b', 'target-arrow-color': '#f59e0b', 'width': 3, 'opacity': 1}}
                }}
            ],
            layout: {{
                name: 'cose',
                directed: true,
                animate: true,
                animationDuration: 500
            }}
        }});

        function updateInfo(nodeId) {{
            const node = cy.$('#' + nodeId);
            const outgoing = node.outgoers().nodes().map(n => n.id());
            const incoming = node.incomers().nodes().map(n => n.id());

            let html = '<h2><i class="fas fa-file-code"></i> Focused Node</h2>';
            html += '<div class="focused-node">' + nodeId + '</div>';

            html += '<div class="section">';
            html += '<div class="section-title"><i class="fas fa-arrow-down"></i> Who Depends On This</div>';
            if (incoming.length > 0) {{
                incoming.forEach(id => {{
                    html += '<div class="item"><i class="fas fa-link"></i> ' + id + '</div>';
                }});
            }} else {{
                html += '<div class="item" style="border-left-color: #cbd5e1; background: #f1f5f9; color: #94a3b8;"><i class="fas fa-check-circle"></i> No dependents</div>';
            }}
            html += '</div>';

            html += '<div class="section">';
            html += '<div class="section-title"><i class="fas fa-arrow-up"></i> Dependencies</div>';
            if (outgoing.length > 0) {{
                outgoing.forEach(id => {{
                    html += '<div class="item"><i class="fas fa-link"></i> ' + id + '</div>';
                }});
            }} else {{
                html += '<div class="item" style="border-left-color: #cbd5e1; background: #f1f5f9; color: #94a3b8;"><i class="fas fa-check-circle"></i> No dependencies</div>';
            }}
            html += '</div>';

            const blastRadius = incoming.length + outgoing.length;
            html += '<div class="metrics">';
            html += '<div class="section-title"><i class="fas fa-chart-bar"></i> Metrics</div>';
            html += '<div class="stat"><span><i class="fas fa-bomb"></i> Blast Radius</span><span class="stat-value">' + blastRadius + '</span></div>';
            html += '<div class="stat"><span><i class="fas fa-arrow-down"></i> Dependents</span><span class="stat-value">' + incoming.length + '</span></div>';
            html += '<div class="stat"><span><i class="fas fa-arrow-up"></i> Dependencies</span><span class="stat-value">' + outgoing.length + '</span></div>';
            html += '</div>';

            document.getElementById('info').innerHTML = html;

            cy.elements().removeClass('focused parent child');
            node.addClass('focused');
            node.incomers().nodes().addClass('parent');
            node.outgoers().nodes().addClass('child');
            cy.edges().forEach(e => {{
                if (e.source().id() === nodeId || e.target().id() === nodeId) {{
                    e.addClass('focused');
                }}
            }});
        }}

        cy.on('tap', 'node', function() {{
            updateInfo(this.id());
        }});

        document.getElementById('reset').addEventListener('click', function() {{
            cy.elements().removeClass('focused parent child');
            cy.fit();
            document.getElementById('info').innerHTML = '<h2>Select a node</h2><p style="color: #999; font-size: 12px;">Click on any file to see its dependencies</p>';
        }});

        document.getElementById('search').addEventListener('input', function(e) {{
            const query = e.target.value.toLowerCase();
            cy.elements().removeClass('highlight');
            if (query) {{
                cy.nodes().forEach(n => {{
                    if (n.id().toLowerCase().includes(query)) {{
                        n.addClass('highlight');
                    }}
                }});
            }}
        }});

        cy.fit();
        cy.zoom(1.2);

        // Theme Toggle
        const themeToggle = document.getElementById('theme-toggle');
        const htmlElement = document.documentElement;
        const currentTheme = localStorage.getItem('theme') || 'dark';

        // Set initial theme
        if (currentTheme === 'light') {{
            document.body.classList.add('light-mode');
            themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
        }}

        themeToggle.addEventListener('click', function() {{
            const body = document.body;
            const isLightMode = body.classList.contains('light-mode');

            if (isLightMode) {{
                body.classList.remove('light-mode');
                themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
                localStorage.setItem('theme', 'dark');
            }} else {{
                body.classList.add('light-mode');
                themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
                localStorage.setItem('theme', 'light');
            }}

            // Refresh Cytoscape to match new theme
            setTimeout(() => cy.redraw(), 100);
        }});

        // ── Mind Map ──────────────────────────────────────────────
        const GROUP_COLORS = {{
            'root':         {{ bg: '#f59e0b', border: '#d97706' }},
            'scanners':     {{ bg: '#10b981', border: '#059669' }},
            'code-analyzer':{{ bg: '#06b6d4', border: '#0891b2' }},
            'vue-uiux':     {{ bg: '#a78bfa', border: '#7c3aed' }},
            'gemini':       {{ bg: '#f472b6', border: '#db2777' }},
            'vscode':       {{ bg: '#fb923c', border: '#ea580c' }},
            'other':        {{ bg: '#667eea', border: '#4f46e5' }}
        }};
        function getGroup(id) {{
            if (id.startsWith('scanners/'))          return 'scanners';
            if (id.startsWith('code-analyzer/'))     return 'code-analyzer';
            if (id.startsWith('vue-uiux-analyzer/')) return 'vue-uiux';
            if (id.startsWith('gemini-chatbot/'))    return 'gemini';
            if (id.startsWith('vscode-extension/'))  return 'vscode';
            if (!id.includes('/'))                   return 'root';
            return 'other';
        }}
        let mmCy = null;
        function buildMindMapData() {{
            const nodes = [], edges = [];
            cy.nodes().forEach(n => {{
                const id = n.id(), grp = getGroup(id), col = GROUP_COLORS[grp];
                nodes.push({{ data: {{ id, label: n.data('label'), group: grp, weight: n.degree() }},
                              style: {{ 'background-color': col.bg, 'border-color': col.border }} }});
            }});
            cy.edges().forEach(e => {{
                edges.push({{ data: {{ id: 'mm-'+e.id(), source: e.source().id(), target: e.target().id() }} }});
            }});
            return nodes.concat(edges);
        }}
        function applyLayout(name) {{
            if (!mmCy) return;
            document.querySelectorAll('.mm-layout-btn').forEach(b => b.classList.toggle('active', b.dataset.layout===name));
            const opts = name === 'concentric' ? {{
                name:'concentric', concentric: n=>n.data('weight')+1, levelWidth:()=>3,
                minNodeSpacing:40, animate:true, animationDuration:600, padding:60
            }} : name === 'breadthfirst' ? {{
                name:'breadthfirst', directed:true, animate:true, animationDuration:600, spacingFactor:1.4, padding:50
            }} : {{
                name:'cose', animate:true, animationDuration:700, nodeRepulsion:()=>8000, padding:50
            }};
            mmCy.layout(opts).run();
        }}
        function openMindMap() {{
            const modal = document.getElementById('mindmap-modal');
            modal.style.display = 'block'; modal.classList.remove('closing');
            if (mmCy) {{ mmCy.destroy(); mmCy = null; }}
            mmCy = cytoscape({{
                container: document.getElementById('mindmap-canvas'),
                elements: buildMindMapData(),
                style: [
                    {{ selector:'node', style:{{'content':'data(label)','color':'#fff','text-valign':'center',
                        'text-halign':'center','font-size':10,'font-weight':'700','padding':'10px',
                        'border-width':2,'text-wrap':'wrap','text-max-width':'90px',
                        'shadow-blur':12,'shadow-color':'rgba(0,0,0,0.5)','shadow-offset-x':0,'shadow-offset-y':3}} }},
                    {{ selector:'node:selected', style:{{'border-width':4,'shadow-blur':24}} }},
                    {{ selector:'edge', style:{{'curve-style':'bezier','target-arrow-shape':'triangle',
                        'line-color':'rgba(148,163,184,0.4)','target-arrow-color':'rgba(148,163,184,0.4)',
                        'width':1.5,'opacity':0.7}} }},
                    {{ selector:'edge.mm-hi', style:{{'line-color':'#f59e0b','target-arrow-color':'#f59e0b','width':3,'opacity':1}} }}
                ],
                layout: {{name:'preset'}}
            }});
            mmCy.nodes().forEach(n => {{ const col=GROUP_COLORS[getGroup(n.id())]; n.style({{'background-color':col.bg,'border-color':col.border}}); }});
            mmCy.on('mouseover','node',function(){{ mmCy.edges().removeClass('mm-hi'); this.connectedEdges().addClass('mm-hi'); }});
            mmCy.on('mouseout','node',()=>mmCy.edges().removeClass('mm-hi'));
            mmCy.on('tap','node',function(){{
                const id=this.id(); closeMindMap();
                setTimeout(()=>{{ updateInfo(id); const mn=cy.$('#'+CSS.escape(id)); if(mn.length) cy.animate({{fit:{{eles:mn,padding:120}}}},{{duration:400}}); }},300);
            }});
            applyLayout('concentric');
        }}
        function closeMindMap() {{
            const modal=document.getElementById('mindmap-modal');
            modal.classList.add('closing');
            setTimeout(()=>modal.style.display='none',250);
        }}
        document.getElementById('mindmap-btn').addEventListener('click', openMindMap);
        document.getElementById('mindmap-close').addEventListener('click', closeMindMap);
        document.addEventListener('keydown', e=>{{ if(e.key==='Escape') closeMindMap(); }});
        document.querySelectorAll('.mm-layout-btn').forEach(b=>b.addEventListener('click',()=>applyLayout(b.dataset.layout)));
    </script>
</body>
</html>
"""
        html = html.replace('__DATA_PLACEHOLDER__', data_json)
        output_path = self.root_path / output_file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Generated: {output_path}")
        return output_path

    def _build_graph_data(self):
        """Build graph nodes and edges"""
        nodes = []
        edges = []
        seen = set()

        for file_path in self.dependencies.keys():
            if file_path not in seen:
                label = file_path.split('/')[-1]
                nodes.append({
                    'data': {'id': file_path, 'label': label}
                })
                seen.add(file_path)

        for source, targets in self.dependencies.items():
            for target in targets:
                if target not in seen:
                    label = target.split('/')[-1]
                    nodes.append({
                        'data': {'id': target, 'label': label}
                    })
                    seen.add(target)
                edges.append({
                    'data': {'source': source, 'target': target}
                })

        return nodes, edges


def main():
    root_path = os.getcwd()
    visualizer = DependencyVisualizer(root_path)
    visualizer.analyze()
    visualizer.generate_html()
    print("\nOpen DEPENDENCY_GRAPH.html in your browser!")


if __name__ == "__main__":
    main()
