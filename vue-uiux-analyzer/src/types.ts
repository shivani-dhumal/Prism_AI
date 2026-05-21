/**
 * Shared types for the Vue UI/UX Analyzer extension.
 * These mirror the Python data structures used by the analysis engine.
 */

export interface ScanIssue {
  id: string;
  rule_id: string;
  severity: 'low' | 'medium' | 'high';
  category: string;
  message: string;
  description: string;
  file: string;
  line: number;
  column: number;
  end_line: number;
  end_column: number;
  fix?: IssueFix;
  ignored: boolean;
}

export interface IssueFix {
  description: string;
  original: string;
  replacement: string;
  line: number;
  column: number;
  end_line: number;
  end_column: number;
}

export interface ScanResult {
  timestamp: number;
  project_path: string;
  issues: ScanIssue[];
  file_count: number;
  scan_duration: number;
  files_scanned: string[];
}

export interface ScanHistoryEntry {
  id: string;
  timestamp: number;
  project_path: string;
  total_issues: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  file_count: number;
}

export interface FileIssues {
  file: string;
  issues: ScanIssue[];
}

export type WebviewMessage =
  | { command: 'scan'; path?: string }
  | { command: 'scanFile'; path: string }
  | { command: 'fix'; file: string; issueId: string }
  | { command: 'fixAll'; file?: string }
  | { command: 'ignore'; issueId: string; ruleId: string }
  | { command: 'rescan' }
  | { command: 'exportReport'; format: 'json' | 'html' }
  | { command: 'getHistory' }
  | { command: 'clearCache' }
  | { command: 'openFile'; file: string; line: number };

export type ExtensionMessage =
  | { command: 'scanResults'; data: ScanResult }
  | { command: 'scanProgress'; message: string; percent: number }
  | { command: 'history'; data: ScanHistoryEntry[] }
  | { command: 'error'; message: string }
  | { command: 'fixApplied'; issueId: string; success: boolean }
  | { command: 'info'; message: string };
