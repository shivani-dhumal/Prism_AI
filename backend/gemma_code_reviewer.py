#!/usr/bin/env python3
"""
Gemma API Code Reviewer
Reviews code files for UI consistency and accessibility issues
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

try:
    import google.generativeai as genai
    GEMMA_AVAILABLE = True
except ImportError:
    GEMMA_AVAILABLE = False
    print("Install: pip install google-generativeai")


class GemmaCodeReviewer:
    def __init__(self, api_key: Optional[str] = None, use_gemini: bool = True):
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY')
        if self.api_key:
            genai.configure(api_key=self.api_key)
            # Use Gemini for better code analysis
            self.model = genai.GenerativeModel('gemini-1.5-flash' if use_gemini else 'gemma-2-9b-it')
            self.model_name = 'Gemini 1.5 Flash' if use_gemini else 'Gemma 2'
        else:
            self.model = None
            self.model_name = None

    def review_file(self, file_path: str) -> dict:
        """Review a single file for UI/accessibility issues"""
        file_path = Path(file_path)

        if not file_path.exists():
            return {"error": f"File not found: {file_path}"}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
        except Exception as e:
            return {"error": f"Could not read file: {e}"}

        if not self.model:
            return {"error": "Gemma API not configured. Set GOOGLE_API_KEY environment variable"}

        prompt = self._build_prompt(file_path, code)

        try:
            response = self.model.generate_content(prompt)
            analysis = response.text
        except Exception as e:
            return {"error": f"API Error: {e}"}

        return {
            "file": str(file_path),
            "analysis": analysis,
            "status": "success"
        }

    def _build_prompt(self, file_path: Path, code: str) -> str:
        """Build minimal focused prompt"""
        prompt = f"""Review {file_path.name} for ACCESSIBILITY and UI CONSISTENCY issues only.

```
{code}
```

Find:
1. Accessibility (WCAG 2.1 AA): missing alt, labels, contrast, aria, semantic HTML, keyboard nav
2. UI Consistency: buttons, spacing, colors, fonts, icons, responsive design

Format:
## CRITICAL
- [Line] Issue → Fix

## HIGH
- [Line] Issue → Fix

## MEDIUM
- [Line] Issue → Fix

## LOW
- [Line] Issue → Fix

Be specific. Only real issues."""
        return prompt

    def review_directory(self, directory: str, pattern: str = "*.vue"):
        """Review all matching files in directory"""
        dir_path = Path(directory)
        results = []

        files = list(dir_path.rglob(pattern))
        total = len(files)

        print(f"Found {total} files matching '{pattern}'")
        print("=" * 60)

        for i, file_path in enumerate(files, 1):
            # Skip common non-code files
            if any(x in str(file_path) for x in ['__pycache__', 'node_modules', '.git']):
                continue

            print(f"\n[{i}/{total}] Reviewing: {file_path.relative_to(dir_path)}")

            result = self.review_file(file_path)
            if result.get("status") == "success":
                results.append({
                    "file": str(file_path.relative_to(dir_path)),
                    "analysis": result["analysis"]
                })
                print(f"✓ Completed")
            else:
                print(f"✗ {result.get('error', 'Unknown error')}")

        return results

    def generate_report(self, results: list, output_file: str = "GEMMA_REVIEW_REPORT.html"):
        """Generate HTML report"""
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Code Review Report - Gemma Analysis</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h1 { color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }
        .file-review { margin: 30px 0; padding: 20px; background: #f9f9f9; border-left: 4px solid #007bff; border-radius: 4px; }
        .file-name { font-size: 18px; font-weight: bold; color: #007bff; margin-bottom: 15px; }
        .analysis { white-space: pre-wrap; font-family: 'Monaco', 'Courier New', monospace; font-size: 13px; line-height: 1.6; background: white; padding: 15px; border-radius: 4px; overflow-x: auto; }
        .critical { color: #d32f2f; font-weight: bold; }
        .high { color: #f57c00; font-weight: bold; }
        .medium { color: #fbc02d; font-weight: bold; }
        .low { color: #388e3c; font-weight: bold; }
        hr { border: none; border-top: 1px solid #eee; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Code Review Report - Gemini Analysis</h1>
        <p>Generated using Gemini API for UI consistency and accessibility review</p>
        <hr>
"""

        for result in results:
            html += f"""
        <div class="file-review">
            <div class="file-name">{result['file']}</div>
            <div class="analysis">{result['analysis']}</div>
        </div>
"""

        html += """
    </div>
</body>
</html>
"""

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"\n✓ Report saved to: {output_file}")
        return output_file


def main():
    if not GEMMA_AVAILABLE:
        print("ERROR: google-generativeai not installed")
        print("Run: pip install google-generativeai")
        return

    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        print("ERROR: GOOGLE_API_KEY environment variable not set")
        print("Set it: $env:GOOGLE_API_KEY = 'your-api-key'")
        return

    reviewer = GemmaCodeReviewer(api_key, use_gemini=True)

    # Review Vue files in the project
    print("Gemini Code Reviewer - UI/Accessibility Analysis")
    print("=" * 60)

    results = reviewer.review_directory(
        ".",
        pattern="*.vue"  # Change to *.py, *.js, etc. as needed
    )

    if results:
        reviewer.generate_report(results)
    else:
        print("No files reviewed or all failed.")


if __name__ == "__main__":
    main()
