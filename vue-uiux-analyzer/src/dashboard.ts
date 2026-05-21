import * as vscode from 'vscode';
import { ExtensionMessage, WebviewMessage } from './types';
import { PythonEngine } from './pythonEngine';

/**
 * DashboardPanel — Iframe-based Webview Architecture
 * ===================================================
 * Instead of building a complex Webview-specific UI, this creates a simple
 * HTML wrapper that loads the Vue.js frontend (served by Flask at localhost)
 * inside an iframe.
 *
 * How it works:
 * 1. The Wrapper: This class creates a basic Webview container in VS Code.
 * 2. The Content (Vue.js): It loads http://localhost:5001 via an iframe.
 *    This is the main Vue.js application (located in the web/ folder).
 * 3. Communication: A small JavaScript bridge inside the Webview listens
 *    for window.postMessage events from the Vue app (inside the iframe)
 *    and forwards them to the VS Code Extension API using
 *    acquireVsCodeApi().postMessage(). This is how the Vue app can tell
 *    VS Code to "open a file" or "apply a code fix".
 */
export class DashboardPanel {
  public static currentPanel: DashboardPanel | undefined;
  private readonly _panel: vscode.WebviewPanel;
  private readonly _extensionUri: vscode.Uri;
  private _disposables: vscode.Disposable[] = [];
  private _pythonEngine: PythonEngine;

  /** The port where the Flask server is running */
  private static readonly FRONTEND_PORT = 5001;

  private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri, pythonEngine: PythonEngine) {
    this._panel = panel;
    this._extensionUri = extensionUri;
    this._pythonEngine = pythonEngine;

    // Set the webview's initial HTML (iframe wrapper)
    this._update();

    // Listen for when the panel is disposed
    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

    // Handle messages from the webview (forwarded from the iframe via the bridge)
    this._panel.webview.onDidReceiveMessage(
      async (message: WebviewMessage) => {
        switch (message.command) {
          case 'scan':
            await this._handleScan();
            return;

          case 'scanFile':
            await this._handleScanFile(message.path);
            return;

          case 'fix':
            await this._handleFix(message.file, message.issueId);
            return;

          case 'getHistory':
            await this._handleGetHistory();
            return;

          case 'openFile':
            await this._handleOpenFile(message.file, message.line);
            return;
        }
      },
      null,
      this._disposables
    );
  }

  // ─── Command Handlers ──────────────────────────────

  private async _handleScan() {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (workspaceFolders && workspaceFolders.length > 0) {
      const rootPath = workspaceFolders[0].uri.fsPath;
      this.sendMessage({ command: 'scanProgress', message: 'Starting scan...', percent: 10 });

      try {
        const result = await this._pythonEngine.scanProject(rootPath);
        if (result) {
          this.sendMessage({ command: 'scanResults', data: result });
        }
      } catch (error) {
        vscode.window.showErrorMessage(`Scan failed: ${error}`);
        this.sendMessage({ command: 'error', message: String(error) });
      }
    } else {
      vscode.window.showErrorMessage('No workspace folder open to scan.');
    }
  }

  private async _handleScanFile(filePath: string) {
    this.sendMessage({ command: 'scanProgress', message: 'Scanning file...', percent: 50 });
    try {
      const result = await this._pythonEngine.scanFile(filePath);
      if (result) {
        this.sendMessage({ command: 'scanResults', data: result });
      }
    } catch (error) {
      vscode.window.showErrorMessage(`Scan failed: ${error}`);
      this.sendMessage({ command: 'error', message: String(error) });
    }
  }

  private async _handleFix(file: string, issueId: string) {
    try {
      const result = await this._pythonEngine.applyFix(file, issueId);
      if (result && result.success) {
        vscode.window.showInformationMessage('Fix applied successfully.');
        this.sendMessage({ command: 'fixApplied', issueId: issueId, success: true });
        // Rescan the file to update the UI
        const newScan = await this._pythonEngine.scanFile(file);
        if (newScan) {
          this.sendMessage({ command: 'scanResults', data: newScan });
        }
      } else {
        vscode.window.showErrorMessage(`Failed to apply fix: ${result?.error || 'Unknown error'}`);
      }
    } catch (error) {
      vscode.window.showErrorMessage(`Fix failed: ${error}`);
    }
  }

  private async _handleGetHistory() {
    try {
      const history = await this._pythonEngine.getHistory();
      if (history) {
        this.sendMessage({ command: 'history', data: history });
      }
    } catch (error) {
      console.error('Failed to get history:', error);
    }
  }

  private async _handleOpenFile(filePath: string, line: number) {
    try {
      const uri = vscode.Uri.file(filePath);
      const document = await vscode.workspace.openTextDocument(uri);
      const editor = await vscode.window.showTextDocument(document);

      // Move cursor to the line
      if (line > 0) {
        const position = new vscode.Position(line - 1, 0);
        editor.selection = new vscode.Selection(position, position);
        editor.revealRange(new vscode.Range(position, position), vscode.TextEditorRevealType.InCenter);
      }
    } catch (error) {
      vscode.window.showErrorMessage(`Could not open file: ${filePath}`);
    }
  }

  // ─── Panel Lifecycle ───────────────────────────────

  public static createOrShow(extensionUri: vscode.Uri, pythonEngine: PythonEngine) {
    const column = vscode.window.activeTextEditor
      ? vscode.window.activeTextEditor.viewColumn
      : undefined;

    // If we already have a panel, show it.
    if (DashboardPanel.currentPanel) {
      DashboardPanel.currentPanel._panel.reveal(column);
      return;
    }

    // Otherwise, create a new panel.
    const panel = vscode.window.createWebviewPanel(
      'vueUiUxAnalyzer.dashboard',
      'PrismAI Code Analyzer',
      column || vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true, // Keep state when tab is hidden
        // Allow iframe to load from localhost
        localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'resources')],
      }
    );

    DashboardPanel.currentPanel = new DashboardPanel(panel, extensionUri, pythonEngine);
  }

  public sendMessage(message: ExtensionMessage) {
    this._panel.webview.postMessage(message);
  }

  /**
   * Generate the webview HTML content.
   *
   * Architecture:
   *   ┌─────────────────────────────────────────────────┐
   *   │  VS Code Webview                                │
   *   │  ┌───────────────────────────────────────────┐  │
   *   │  │  <iframe src="http://localhost:5001">      │  │
   *   │  │     Vue.js Frontend (CodeGuard Pro)       │  │
   *   │  │     - File tree, code viewer, issues      │  │
   *   │  │     - Communicates via window.postMessage  │  │
   *   │  └───────────────────────────────────────────┘  │
   *   │                                                 │
   *   │  Bridge Script:                                 │
   *   │  - Listens for postMessage from iframe          │
   *   │  - Forwards to acquireVsCodeApi().postMessage() │
   *   │  - Also forwards VS Code messages back to       │
   *   │    iframe via contentWindow.postMessage()       │
   *   └─────────────────────────────────────────────────┘
   */
  private _update() {
    const webview = this._panel.webview;
    this._panel.title = 'PrismAI Analyzer';

    const port = DashboardPanel.FRONTEND_PORT;
    const workspacePath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
    // Encode workspace path for use in URL query parameter
    const encodedPath = encodeURIComponent(workspacePath.replace(/\\/g, '/'));

    webview.html = `<!DOCTYPE html>
<html lang="en" style="height:100%;margin:0;padding:0;">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PrismAI Code Analyzer</title>
  <style>
    html, body {
      height: 100%;
      margin: 0;
      padding: 0;
      overflow: hidden;
      background: var(--vscode-editor-background, #1e1e1e);
    }

    #app-frame {
      width: 100%;
      height: 100%;
      border: none;
    }

    /* Loading overlay shown while iframe loads */
    #loading-overlay {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background: var(--vscode-editor-background, #1e1e1e);
      color: var(--vscode-editor-foreground, #ccc);
      font-family: var(--vscode-font-family, sans-serif);
      z-index: 1000;
      transition: opacity 0.3s ease;
    }

    #loading-overlay.hidden {
      opacity: 0;
      pointer-events: none;
    }

    .spinner {
      width: 36px;
      height: 36px;
      border: 3px solid rgba(255,255,255,0.1);
      border-top-color: #42b883;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin-bottom: 16px;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .load-text {
      font-size: 14px;
      font-weight: 500;
      margin-bottom: 6px;
    }

    .load-sub {
      font-size: 11px;
      opacity: 0.6;
    }

    /* Error state */
    #error-panel {
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background: var(--vscode-editor-background, #1e1e1e);
      color: var(--vscode-editor-foreground, #ccc);
      font-family: var(--vscode-font-family, sans-serif);
      z-index: 1001;
      text-align: center;
      padding: 40px;
    }

    #error-panel h2 {
      color: #ff6b6b;
      margin-bottom: 12px;
      font-size: 18px;
    }

    #error-panel p {
      opacity: 0.8;
      margin-bottom: 20px;
      max-width: 400px;
      line-height: 1.6;
    }

    #error-panel button {
      background: #42b883;
      color: #fff;
      border: none;
      padding: 8px 20px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      font-family: inherit;
    }

    #error-panel button:hover {
      background: #38a373;
    }
  </style>
</head>
<body>
  <!-- Loading overlay -->
  <div id="loading-overlay">
    <div class="spinner"></div>
    <div class="load-text">Connecting to PrismAI Analyzer...</div>
    <div class="load-sub">Waiting for Flask server on port ${port}</div>
  </div>

  <!-- Error panel (shown if server is not reachable) -->
  <div id="error-panel">
    <h2>Server Not Running</h2>
    <p>
      The Flask development server is not running on
      <strong>http://localhost:${port}</strong>.<br><br>
      Start it by running:<br>
      <code style="background:rgba(255,255,255,0.1);padding:4px 10px;border-radius:4px;font-size:13px;">
        python app.py
      </code><br>
      inside the <strong>vue-uiux-analyzer</strong> folder.
    </p>
    <button onclick="location.reload()">Retry Connection</button>
  </div>

  <!-- The iframe loads the Vue.js frontend served by Flask -->
  <iframe
    id="app-frame"
    src="http://localhost:${port}?vscode=true&path=${encodedPath}"
    frameborder="0"
    allow="clipboard-write"
  ></iframe>

  <script>
    // ─────────────────────────────────────────────
    // VS Code ↔ Iframe postMessage Bridge
    // ─────────────────────────────────────────────

    const vscode = acquireVsCodeApi();
    const iframe = document.getElementById('app-frame');
    const loadingOverlay = document.getElementById('loading-overlay');
    const errorPanel = document.getElementById('error-panel');

    // Track connection state
    let iframeLoaded = false;
    let connectionTimeout = null;

    // ── 1. Iframe → VS Code ──────────────────────
    // Listen for postMessage events from the Vue app (inside the iframe)
    // and forward them to the VS Code Extension API.
    window.addEventListener('message', (event) => {
      // Only accept messages from the iframe (localhost origin)
      if (event.source === iframe.contentWindow) {
        // Forward the message to VS Code extension host
        vscode.postMessage(event.data);
      }

      // Messages from VS Code extension host → forward to iframe
      if (event.source === window && event.data && event.data.command) {
        // This is a message from the extension (via panel.webview.postMessage)
        // Forward it to the iframe
        if (iframe.contentWindow) {
          iframe.contentWindow.postMessage(event.data, '*');
        }
      }
    });

    // ── 2. VS Code → Iframe ──────────────────────
    // The extension sends messages via panel.webview.postMessage(),
    // which arrive as 'message' events on window. We need to
    // forward them into the iframe.
    // (Handled in the message listener above)

    // ── 3. Iframe Load Handling ──────────────────
    iframe.addEventListener('load', () => {
      iframeLoaded = true;
      clearTimeout(connectionTimeout);
      // Hide loading overlay with a short delay for smooth transition
      setTimeout(() => {
        loadingOverlay.classList.add('hidden');
      }, 300);
    });

    iframe.addEventListener('error', () => {
      showError();
    });

    // Timeout: if iframe doesn't load in 8 seconds, show error
    connectionTimeout = setTimeout(() => {
      if (!iframeLoaded) {
        showError();
      }
    }, 8000);

    function showError() {
      loadingOverlay.style.display = 'none';
      errorPanel.style.display = 'flex';
    }
  </script>
</body>
</html>`;
  }

  public dispose() {
    DashboardPanel.currentPanel = undefined;
    this._panel.dispose();

    while (this._disposables.length) {
      const x = this._disposables.pop();
      if (x) {
        x.dispose();
      }
    }
  }
}
