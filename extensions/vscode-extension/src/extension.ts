import * as vscode from 'vscode';
import * as path from 'path';
import axios from 'axios';

let dashboardPanel: vscode.WebviewPanel | undefined;
let analysisPanel: vscode.WebviewPanel | undefined;

export function activate(context: vscode.ExtensionContext) {
	console.log('PrismAI extension activated');

	// Dashboard command
	context.subscriptions.push(
		vscode.commands.registerCommand('prismia.openDashboard', () => {
			openDashboardWebview(context);
		})
	);

	// Analyze file command
	context.subscriptions.push(
		vscode.commands.registerCommand('prismia.analyzeFile', (uri: vscode.Uri) => {
			if (uri) {
				analyzeFile(uri, context);
			} else if (vscode.window.activeTextEditor) {
				analyzeFile(vscode.window.activeTextEditor.document.uri, context);
			}
		})
	);

	// Show architecture command
	context.subscriptions.push(
		vscode.commands.registerCommand('prismia.showArchitecture', () => {
			openArchitectureWebview(context);
		})
	);

	// Show dependencies command
	context.subscriptions.push(
		vscode.commands.registerCommand('prismia.showDependencies', () => {
			openDependenciesWebview(context);
		})
	);

	// Show audit report command
	context.subscriptions.push(
		vscode.commands.registerCommand('prismia.showAudit', () => {
			openAuditWebview(context);
		})
	);
}

function openDashboardWebview(context: vscode.ExtensionContext) {
	if (dashboardPanel) {
		dashboardPanel.reveal(vscode.ViewColumn.One);
		return;
	}

	dashboardPanel = vscode.window.createWebviewPanel(
		'prismia-dashboard',
		'PrismAI Dashboard',
		vscode.ViewColumn.One,
		{
			enableScripts: true,
			localResourceRoots: [vscode.Uri.file(path.join(context.extensionPath, 'media'))],
			retainContextWhenHidden: true
		}
	);

	const serverUrl = vscode.workspace.getConfiguration('prismia').get('serverUrl') as string;

	dashboardPanel.webview.html = getDashboardHtml(serverUrl);

	dashboardPanel.onDidDispose(() => {
		dashboardPanel = undefined;
	}, null, context.subscriptions);
}

function openArchitectureWebview(context: vscode.ExtensionContext) {
	if (analysisPanel) {
		analysisPanel.reveal(vscode.ViewColumn.One);
		analysisPanel.webview.postMessage({ type: 'navigate', page: 'architecture' });
		return;
	}

	analysisPanel = vscode.window.createWebviewPanel(
		'prismia-analysis',
		'PrismAI Architecture',
		vscode.ViewColumn.One,
		{
			enableScripts: true,
			localResourceRoots: [vscode.Uri.file(path.join(context.extensionPath, 'media'))],
			retainContextWhenHidden: true
		}
	);

	const serverUrl = vscode.workspace.getConfiguration('prismia').get('serverUrl') as string;

	analysisPanel.webview.html = getAnalysisHtml(serverUrl, 'architecture');

	analysisPanel.onDidDispose(() => {
		analysisPanel = undefined;
	}, null, context.subscriptions);
}

function openDependenciesWebview(context: vscode.ExtensionContext) {
	if (analysisPanel) {
		analysisPanel.reveal(vscode.ViewColumn.One);
		analysisPanel.webview.postMessage({ type: 'navigate', page: 'dependencies' });
		return;
	}

	analysisPanel = vscode.window.createWebviewPanel(
		'prismia-analysis',
		'PrismAI Dependencies',
		vscode.ViewColumn.One,
		{
			enableScripts: true,
			localResourceRoots: [vscode.Uri.file(path.join(context.extensionPath, 'media'))],
			retainContextWhenHidden: true
		}
	);

	const serverUrl = vscode.workspace.getConfiguration('prismia').get('serverUrl') as string;

	analysisPanel.webview.html = getAnalysisHtml(serverUrl, 'dependencies');

	analysisPanel.onDidDispose(() => {
		analysisPanel = undefined;
	}, null, context.subscriptions);
}

function openAuditWebview(context: vscode.ExtensionContext) {
	if (analysisPanel) {
		analysisPanel.reveal(vscode.ViewColumn.One);
		analysisPanel.webview.postMessage({ type: 'navigate', page: 'audit' });
		return;
	}

	analysisPanel = vscode.window.createWebviewPanel(
		'prismia-analysis',
		'PrismAI Audit Report',
		vscode.ViewColumn.One,
		{
			enableScripts: true,
			localResourceRoots: [vscode.Uri.file(path.join(context.extensionPath, 'media'))],
			retainContextWhenHidden: true
		}
	);

	const serverUrl = vscode.workspace.getConfiguration('prismia').get('serverUrl') as string;

	analysisPanel.webview.html = getAnalysisHtml(serverUrl, 'audit');

	analysisPanel.onDidDispose(() => {
		analysisPanel = undefined;
	}, null, context.subscriptions);
}

async function analyzeFile(uri: vscode.Uri, context: vscode.ExtensionContext) {
	const filePath = uri.fsPath;
	const serverUrl = vscode.workspace.getConfiguration('prismia').get('serverUrl') as string;

	try {
		const response = await axios.post(`${serverUrl}/api/analyze-file`, {
			file_path: filePath
		});

		if (analysisPanel) {
			analysisPanel.reveal(vscode.ViewColumn.One);
		} else {
			analysisPanel = vscode.window.createWebviewPanel(
				'prismia-file-analysis',
				`PrismAI: ${path.basename(filePath)}`,
				vscode.ViewColumn.Two,
				{
					enableScripts: true,
					localResourceRoots: [vscode.Uri.file(path.join(context.extensionPath, 'media'))],
					retainContextWhenHidden: true
				}
			);

			analysisPanel.onDidDispose(() => {
				analysisPanel = undefined;
			}, null, context.subscriptions);
		}

		analysisPanel.webview.html = getFileAnalysisHtml(serverUrl, filePath, response.data);

		vscode.window.showInformationMessage(`Analysis complete: ${response.data.issues_count} issues found`);
	} catch (error: any) {
		vscode.window.showErrorMessage(`Analysis failed: ${error.message}`);
	}
}

function getDashboardHtml(serverUrl: string): string {
	return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PrismAI Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            padding: 20px;
        }
        h1 {
            font-size: 28px;
            margin-bottom: 20px;
            color: var(--vscode-textLink-foreground);
        }
        p {
            margin-bottom: 12px;
            line-height: 1.5;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin: 20px 0;
        }
        .card {
            background: var(--vscode-sideBar-background);
            border: 1px solid var(--vscode-sideBarSectionHeader-border);
            border-radius: 6px;
            padding: 16px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .card:hover {
            border-color: var(--vscode-textLink-foreground);
            transform: translateY(-2px);
        }
        .card h3 {
            margin-bottom: 8px;
            color: var(--vscode-textLink-foreground);
        }
        .stat {
            font-size: 32px;
            font-weight: bold;
            color: var(--vscode-textLink-foreground);
            margin: 8px 0;
        }
        button {
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            padding: 10px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin: 4px 0;
            transition: all 0.2s;
        }
        button:hover {
            background: var(--vscode-button-hoverBackground);
        }
        .status {
            padding: 12px;
            border-radius: 4px;
            margin: 12px 0;
            background: var(--vscode-inputValidation-infoBackground);
            color: var(--vscode-inputValidation-infoForeground);
        }
    </style>
</head>
<body>
    <h1>🔬 PrismAI</h1>
    <p>Forensic code analysis for your VS Code workspace.</p>

    <div class="grid">
        <div class="card" onclick="openArchitecture()">
            <h3>📊 Architecture</h3>
            <p>View the codebase structure and dependencies</p>
            <button onclick="openArchitecture()">View Map</button>
        </div>

        <div class="card" onclick="openDependencies()">
            <h3>🔗 Dependencies</h3>
            <p>Analyze import topology and circular deps</p>
            <button onclick="openDependencies()">View Graph</button>
        </div>

        <div class="card" onclick="openAudit()">
            <h3>📋 Audit Report</h3>
            <p>Review all findings and issues</p>
            <button onclick="openAudit()">View Report</button>
        </div>

        <div class="card" onclick="analyzeWorkspace()">
            <h3>▶️ Start Scan</h3>
            <p>Run analysis on your workspace</p>
            <button onclick="analyzeWorkspace()">Scan Now</button>
        </div>
    </div>

    <div class="status">
        <strong>Server:</strong> <span id="server">${serverUrl}</span><br>
        <strong>Status:</strong> <span id="status">Checking connection...</span>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        const serverUrl = '${serverUrl}';

        async function checkServer() {
            try {
                const response = await fetch(serverUrl + '/api/health', { mode: 'no-cors' });
                document.getElementById('status').textContent = '✓ Connected';
                document.getElementById('status').style.color = 'var(--vscode-testing-message-error-decorationForeground)';
            } catch {
                document.getElementById('status').textContent = '✗ Disconnected';
            }
        }

        function openArchitecture() {
            vscode.postMessage({ command: 'openArchitecture' });
        }

        function openDependencies() {
            vscode.postMessage({ command: 'openDependencies' });
        }

        function openAudit() {
            vscode.postMessage({ command: 'openAudit' });
        }

        function analyzeWorkspace() {
            vscode.postMessage({ command: 'analyzeWorkspace' });
        }

        checkServer();
        setInterval(checkServer, 5000);
    </script>
</body>
</html>`;
}

function getAnalysisHtml(serverUrl: string, page: string): string {
	return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PrismAI Analysis</title>
    <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
    <script src="https://unpkg.com/cytoscape@3.28.1/dist/cytoscape.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            background: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            overflow: hidden;
        }
        #app { height: 100vh; display: flex; flex-direction: column; }
        .header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--vscode-sideBarSectionHeader-border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .content {
            flex: 1;
            overflow: auto;
            padding: 12px;
        }
        .loading {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100%;
            font-size: 16px;
        }
        #graph {
            width: 100%;
            height: 100%;
            background: var(--vscode-sideBar-background);
        }
        .error {
            color: var(--vscode-errorForeground);
            padding: 16px;
        }
    </style>
</head>
<body>
    <div id="app">
        <div class="header">
            <h2>PrismAI ${page.charAt(0).toUpperCase() + page.slice(1)}</h2>
            <button onclick="location.reload()">↻</button>
        </div>
        <div class="content" id="content">
            <div class="loading">Loading analysis data...</div>
        </div>
    </div>

    <script>
        const serverUrl = '${serverUrl}';
        const page = '${page}';

        async function loadData() {
            try {
                let endpoint = '';
                if (page === 'architecture') endpoint = '/api/architecture';
                else if (page === 'dependencies') endpoint = '/api/dependencies';
                else if (page === 'audit') endpoint = '/api/audit-report';

                const response = await fetch(serverUrl + endpoint);
                const data = await response.json();

                document.getElementById('content').innerHTML =
                    \`<div class="loaded"><pre>\${JSON.stringify(data, null, 2)}</pre></div>\`;
            } catch (error) {
                document.getElementById('content').innerHTML =
                    \`<div class="error">Error loading data: \${error.message}</div>\`;
            }
        }

        loadData();
    </script>
</body>
</html>`;
}

function getFileAnalysisHtml(serverUrl: string, filePath: string, analysis: any): string {
	const findings = (analysis.findings || []).map((f: any) =>
		`<div class="finding"><div class="finding-title">${f.title}</div><div class="finding-line">Line ${f.line}: ${f.severity}</div><div>${f.description}</div></div>`
	).join('');

	return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Analysis: ${path.basename(filePath)}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            background: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            padding: 16px;
        }
        h1 { margin-bottom: 16px; color: var(--vscode-textLink-foreground); }
        .stat {
            display: inline-block;
            background: var(--vscode-sideBar-background);
            padding: 12px 16px;
            margin: 8px 8px 8px 0;
            border-radius: 4px;
            border: 1px solid var(--vscode-sideBarSectionHeader-border);
        }
        .stat-number { font-size: 24px; font-weight: bold; }
        .stat-label { font-size: 12px; opacity: 0.8; }
        .findings {
            margin-top: 20px;
        }
        .finding {
            background: var(--vscode-sideBar-background);
            border-left: 3px solid var(--vscode-editorError-foreground);
            padding: 12px;
            margin: 8px 0;
            border-radius: 2px;
        }
        .finding-title { font-weight: bold; margin-bottom: 4px; }
        .finding-line { font-size: 12px; opacity: 0.7; }
    </style>
</head>
<body>
    <h1>📄 ${path.basename(filePath)}</h1>

    <div class="stat">
        <div class="stat-number">${analysis.issues_count || 0}</div>
        <div class="stat-label">Issues Found</div>
    </div>

    <div class="findings">
        ${findings}
    </div>
</body>
</html>`;
}

export function deactivate() { }
