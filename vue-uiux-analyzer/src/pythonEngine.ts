import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as path from 'path';

export class PythonEngine {
  private _pythonPath: string;
  private _cliPath: string;

  constructor(context: vscode.ExtensionContext) {
    // Get Python path from configuration, default to 'python'
    const config = vscode.workspace.getConfiguration('vueUiUxAnalyzer');
    this._pythonPath = config.get<string>('pythonPath', 'python');
    
    // Path to our python CLI entry point
    this._cliPath = vscode.Uri.joinPath(context.extensionUri, 'python', 'cli.py').fsPath;
  }

  /**
   * Execute a command via the Python CLI and parse the JSON result
   */
  private async executeCommand(args: string[]): Promise<any> {
    return new Promise((resolve, reject) => {
      const processArgs = [this._cliPath, ...args];
      
      cp.execFile(this._pythonPath, processArgs, { maxBuffer: 1024 * 1024 * 10 }, (error, stdout, stderr) => {
        if (error && !stdout) {
          console.error(`Python Engine Error: ${error.message}`);
          console.error(`Stderr: ${stderr}`);
          reject(new Error(`Failed to execute Python engine: ${error.message}\nEnsure Python is installed and configured correctly.`));
          return;
        }

        try {
          // Parse the stdout as JSON
          // We might have other output before the JSON, so find the last JSON object
          const lines = stdout.trim().split('\n');
          const jsonStr = lines[lines.length - 1]; // Assuming CLI prints JSON on the last line
          
          const result = JSON.parse(jsonStr);
          
          if (!result.success) {
            reject(new Error(result.error || 'Unknown error from Python engine'));
            return;
          }
          
          resolve(result.data);
        } catch (parseError) {
          console.error(`Failed to parse Python output: ${stdout}`);
          reject(new Error('Invalid output from Python engine. Ensure dependencies are installed.'));
        }
      });
    });
  }

  public async scanProject(projectPath: string, force: boolean = false): Promise<any> {
    const args = ['scan', projectPath];
    if (force) args.push('--force');
    
    const config = vscode.workspace.getConfiguration('vueUiUxAnalyzer');
    const minSeverity = config.get<string>('minimumSeverity', 'low');
    args.push('--min-severity', minSeverity);
    
    return this.executeCommand(args);
  }

  public async scanFile(filePath: string, force: boolean = false): Promise<any> {
    return this.scanProject(filePath, force); // CLI uses same command
  }

  public async applyFix(filePath: string, issueId?: string, issueData?: any): Promise<any> {
    const args = ['fix', filePath];
    if (issueId) {
      args.push('--issue', issueId);
    }
    
    // In a real implementation we would pass the actual issue data here,
    // but we'll need to fetch it from the engine or pass it from the UI.
    // For now we'll just send an empty list and rely on the engine to handle it,
    // though the CLI expects --data.
    args.push('--data', JSON.stringify([])); 
    
    return this.executeCommand(args);
  }

  public async getHistory(limit: number = 20): Promise<any> {
    return this.executeCommand(['history', '--limit', limit.toString()]);
  }
}
