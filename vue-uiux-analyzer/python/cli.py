"""
CLI Entry Point - Interface for VS Code extension to communicate with the Python engine.
"""

import sys
import json
import argparse
from typing import Dict, Any

from scanner_engine import ScannerEngine
from fix_engine import FixEngine
from scan_history import ScanHistory


def setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Vue UI/UX Analyzer CLI')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Scan a file or project')
    scan_parser.add_argument('path', help='Path to file or directory to scan')
    scan_parser.add_argument('--force', action='store_true', help='Force rescan ignoring cache')
    scan_parser.add_argument('--min-severity', choices=['low', 'medium', 'high'], default='low', help='Minimum severity to report')
    
    # Fix command
    fix_parser = subparsers.add_parser('fix', help='Apply a fix')
    fix_parser.add_argument('file', help='Path to file to fix')
    fix_parser.add_argument('--issue', help='Specific issue ID to fix. If not provided, fixes all.', default=None)
    fix_parser.add_argument('--data', help='JSON string containing issue data for the fix', required=True)
    
    # Rules command
    subparsers.add_parser('rules', help='List available rules')
    
    # History command
    history_parser = subparsers.add_parser('history', help='View scan history')
    history_parser.add_argument('--limit', type=int, default=20, help='Maximum number of entries to return')
    history_parser.add_argument('--id', help='Get full result for specific scan ID')
    
    return parser


def format_output(success: bool, data: Any = None, error: str = None) -> str:
    """Format the output as JSON for VS Code to parse."""
    result = {
        'success': success
    }
    if data is not None:
        result['data'] = data
    if error is not None:
        result['error'] = error
        
    return json.dumps(result)


def main():
    parser = setup_parser()
    args = parser.parse_args()
    
    if not args.command:
        print(format_output(False, error="No command provided"))
        sys.exit(1)
        
    try:
        if args.command == 'scan':
            scanner = ScannerEngine(min_severity=args.min_severity)
            
            import os
            if os.path.isfile(args.path):
                issues = scanner.scan_file(args.path, force=args.force)
                # Format as a mini-result
                data = {
                    'project_path': args.path,
                    'issues': [i.to_dict() for i in issues],
                    'file_count': 1,
                    'files_scanned': [args.path]
                }
                print(format_output(True, data))
            else:
                result = scanner.scan_project(args.path, force=args.force)
                # Save to history
                history = ScanHistory()
                history.add_entry(result)
                print(format_output(True, result))
                
        elif args.command == 'fix':
            try:
                issue_data = json.loads(args.data)
                
                if args.issue:
                    # Single fix
                    if isinstance(issue_data, list):
                        # Find the specific issue
                        issue = next((i for i in issue_data if i.get('id') == args.issue), None)
                        if not issue:
                            print(format_output(False, error=f"Issue {args.issue} not found in provided data"))
                            sys.exit(1)
                    else:
                        issue = issue_data
                        
                    result = FixEngine.apply_fix(args.file, issue)
                    print(format_output(result.get('success', False), result))
                else:
                    # Fix all
                    if not isinstance(issue_data, list):
                        issue_data = [issue_data]
                    result = FixEngine.apply_all_fixes(args.file, issue_data)
                    print(format_output(result.get('success', False), result))
            except json.JSONDecodeError:
                print(format_output(False, error="Invalid JSON data provided for fix"))
                sys.exit(1)
                
        elif args.command == 'rules':
            scanner = ScannerEngine()
            print(format_output(True, scanner.get_rule_info()))
            
        elif args.command == 'history':
            history = ScanHistory()
            if args.id:
                result = history.get_full_result(args.id)
                if result:
                    print(format_output(True, result))
                else:
                    print(format_output(False, error=f"Scan ID {args.id} not found"))
            else:
                print(format_output(True, history.get_history(limit=args.limit)))
                
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(format_output(False, error=str(e), data={'traceback': error_details}))
        sys.exit(1)

if __name__ == '__main__':
    main()
