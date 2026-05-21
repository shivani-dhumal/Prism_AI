import * as vscode from 'vscode';
import { PythonEngine } from './pythonEngine';
import { DashboardPanel } from './dashboard';
import { IssueProvider } from './providers';

export function activate(context: vscode.ExtensionContext) {
  console.log('Vue UI/UX Analyzer is now active!');

  // Initialize the Python Engine bridge
  const pythonEngine = new PythonEngine(context);
  
  // Initialize Providers (Diagnostics + Quick Fixes)
  const issueProvider = new IssueProvider(pythonEngine);
  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider(
      ['vue', 'html'],
      issueProvider,
      { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] }
    )
  );
  context.subscriptions.push(issueProvider.getCollection());

  // Command: Open Dashboard
  const openDashboardCmd = vscode.commands.registerCommand('vueUiUxAnalyzer.openDashboard', () => {
    DashboardPanel.createOrShow(context.extensionUri, pythonEngine);
  });
  context.subscriptions.push(openDashboardCmd);

  // Command: Scan Project
  const scanProjectCmd = vscode.commands.registerCommand('vueUiUxAnalyzer.scanProject', async (uri?: vscode.Uri) => {
    let targetPath = '';
    
    if (uri && uri.fsPath) {
      targetPath = uri.fsPath;
    } else if (vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0) {
      targetPath = vscode.workspace.workspaceFolders[0].uri.fsPath;
    } else {
      vscode.window.showErrorMessage('No workspace folder open.');
      return;
    }

    DashboardPanel.createOrShow(context.extensionUri, pythonEngine);
    if (DashboardPanel.currentPanel) {
      DashboardPanel.currentPanel.sendMessage({ command: 'scanProgress', message: 'Starting project scan...', percent: 10 });
      try {
        const result = await pythonEngine.scanProject(targetPath);
        DashboardPanel.currentPanel.sendMessage({ command: 'scanResults', data: result });
        vscode.window.showInformationMessage(`Vue Analyzer: Found ${result.summary?.total || 0} issues across ${result.file_count || 0} files.`);
      } catch (error) {
        vscode.window.showErrorMessage(`Scan failed: ${error}`);
      }
    }
  });
  context.subscriptions.push(scanProjectCmd);

  // Command: Scan Current File
  const scanFileCmd = vscode.commands.registerCommand('vueUiUxAnalyzer.scanCurrentFile', async () => {
    const editor = vscode.window.activeTextEditor;
    if (editor) {
      await issueProvider.updateDiagnostics(editor.document);
      vscode.window.showInformationMessage('Vue Analyzer: File scan complete.');
    }
  });
  context.subscriptions.push(scanFileCmd);

  // Auto-scan on save
  vscode.workspace.onDidSaveTextDocument(async document => {
    const config = vscode.workspace.getConfiguration('vueUiUxAnalyzer');
    if (config.get<boolean>('enableAutoScan', true)) {
      if (document.languageId === 'vue' || document.languageId === 'html') {
        await issueProvider.updateDiagnostics(document);
      }
    }
  }, null, context.subscriptions);

  // Auto-scan on open
  vscode.workspace.onDidOpenTextDocument(async document => {
    const config = vscode.workspace.getConfiguration('vueUiUxAnalyzer');
    if (config.get<boolean>('scanOnOpen', false)) {
      if (document.languageId === 'vue' || document.languageId === 'html') {
        await issueProvider.updateDiagnostics(document);
      }
    }
  }, null, context.subscriptions);

  // Scan currently open editors on activation
  const config = vscode.workspace.getConfiguration('vueUiUxAnalyzer');
  if (config.get<boolean>('scanOnOpen', false)) {
    vscode.window.visibleTextEditors.forEach(editor => {
      if (editor.document.languageId === 'vue' || editor.document.languageId === 'html') {
        issueProvider.updateDiagnostics(editor.document);
      }
    });
  }
}

export function deactivate() {
  // Clean up resources if necessary
}
