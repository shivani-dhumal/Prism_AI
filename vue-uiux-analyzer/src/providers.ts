import * as vscode from 'vscode';
import { PythonEngine } from './pythonEngine';
import { ScanIssue } from './types';
import { DashboardPanel } from './dashboard';

export class IssueProvider implements vscode.CodeActionProvider {
  private diagnosticCollection: vscode.DiagnosticCollection;
  private pythonEngine: PythonEngine;
  private currentIssues: Map<string, ScanIssue[]> = new Map();

  constructor(pythonEngine: PythonEngine) {
    this.diagnosticCollection = vscode.languages.createDiagnosticCollection('vue-uiux-analyzer');
    this.pythonEngine = pythonEngine;
  }

  public getCollection(): vscode.DiagnosticCollection {
    return this.diagnosticCollection;
  }

  public async updateDiagnostics(document: vscode.TextDocument): Promise<void> {
    if (document.languageId !== 'vue' && document.languageId !== 'html') {
      return;
    }

    try {
      const result = await this.pythonEngine.scanFile(document.uri.fsPath);
      
      if (!result || !result.issues) {
        this.diagnosticCollection.set(document.uri, []);
        this.currentIssues.delete(document.uri.fsPath);
        return;
      }

      this.currentIssues.set(document.uri.fsPath, result.issues);

      const diagnostics: vscode.Diagnostic[] = [];

      for (const issue of result.issues) {
        if (issue.ignored) continue;

        // Python uses 1-indexed lines/columns, VS Code uses 0-indexed
        const startLine = Math.max(0, issue.line - 1);
        const startCol = Math.max(0, issue.column - 1);
        const endLine = Math.max(0, issue.end_line - 1);
        const endCol = Math.max(0, issue.end_column - 1);

        const range = new vscode.Range(
          new vscode.Position(startLine, startCol),
          new vscode.Position(endLine, endCol)
        );

        let severity = vscode.DiagnosticSeverity.Warning;
        if (issue.severity === 'high') {
          severity = vscode.DiagnosticSeverity.Error;
        } else if (issue.severity === 'low') {
          severity = vscode.DiagnosticSeverity.Information;
        }

        const diagnostic = new vscode.Diagnostic(
          range,
          `${issue.message}\n${issue.description}`,
          severity
        );

        diagnostic.source = 'Vue UI/UX Analyzer';
        diagnostic.code = issue.rule_id;
        
        // Attach the issue ID so we can use it in quick fixes
        (diagnostic as any).issueId = issue.id;

        diagnostics.push(diagnostic);
      }

      this.diagnosticCollection.set(document.uri, diagnostics);
      
      // Update dashboard if open
      if (DashboardPanel.currentPanel) {
        DashboardPanel.currentPanel.sendMessage({ command: 'scanResults', data: result });
      }

    } catch (error) {
      console.error('Failed to update diagnostics:', error);
    }
  }

  public provideCodeActions(
    document: vscode.TextDocument,
    range: vscode.Range | vscode.Selection,
    context: vscode.CodeActionContext,
    token: vscode.CancellationToken
  ): vscode.ProviderResult<(vscode.CodeAction | vscode.Command)[]> {
    
    const actions: vscode.CodeAction[] = [];
    const issues = this.currentIssues.get(document.uri.fsPath) || [];

    for (const diagnostic of context.diagnostics) {
      if (diagnostic.source !== 'Vue UI/UX Analyzer') {
        continue;
      }

      const issueId = (diagnostic as any).issueId;
      const issue = issues.find(i => i.id === issueId);

      if (issue && issue.fix) {
        const action = new vscode.CodeAction(
          `Fix: ${issue.fix.description}`,
          vscode.CodeActionKind.QuickFix
        );
        
        action.edit = new vscode.WorkspaceEdit();
        
        // Convert python 1-indexed to VS Code 0-indexed
        const fixRange = new vscode.Range(
          new vscode.Position(issue.fix.line - 1, issue.fix.column - 1),
          new vscode.Position(issue.fix.end_line - 1, issue.fix.end_column - 1)
        );
        
        action.edit.replace(document.uri, fixRange, issue.fix.replacement);
        action.diagnostics = [diagnostic];
        action.isPreferred = true;
        
        actions.push(action);
      }
    }

    return actions;
  }
}
