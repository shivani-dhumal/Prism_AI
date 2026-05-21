# Vue UI/UX Analyzer - VS Code Extension

A production-ready Visual Studio Code extension that analyzes Vue.js projects for UI/UX and accessibility issues, providing actionable fixes with a single click.

## Features

| Feature | Description |
|---|---|
| **14 Analysis Rules** | Accessibility, contrast, semantics, responsiveness, styling, and Vue-specific checks |
| **Quick Fixes** | One-click auto-fix via the VS Code lightbulb menu |
| **Problems Panel** | All issues appear as native VS Code warnings/errors |
| **Dashboard UI** | Beautiful Vue 3-powered sidebar showing issues grouped by file |
| **Scan History** | Previous scan results are stored and browsable |
| **Caching** | Only re-scans modified files for fast incremental analysis |
| **Auto-scan on Save** | Optionally scan every Vue/HTML file on save |

## Getting Started

### Prerequisites
- **Python 3.8+** installed and available in your PATH
- **VS Code 1.67+**

### Usage

1. **Reload VS Code** after installation (`Ctrl+Shift+P` → `Developer: Reload Window`)
2. Open any Vue.js project folder
3. Run **`Vue Analyzer: Scan Entire Project`** from the command palette (`Ctrl+Shift+P`)
4. View results in:
   - The **Problems panel** (`Ctrl+Shift+M`)
   - The **Vue UI/UX Analyzer sidebar** (activity bar icon)
   - **Inline hover** on highlighted code

### Commands

| Command | Description |
|---|---|
| `Vue Analyzer: Scan Entire Project` | Scan all `.vue`, `.html`, `.css`, `.js`, `.ts` files |
| `Vue Analyzer: Scan Current File` | Scan the active editor file |
| `Vue Analyzer: Open Dashboard` | Open the full dashboard panel |
| `Vue Analyzer: Fix All Issues in File` | Apply all auto-fixes |
| `Vue Analyzer: Clear Cache` | Reset the scan cache |
| `Vue Analyzer: Export Report` | Export results as JSON/HTML |

### Settings

| Setting | Default | Description |
|---|---|---|
| `vueUiUxAnalyzer.enableAutoScan` | `true` | Auto-scan on file save |
| `vueUiUxAnalyzer.minimumSeverity` | `low` | Minimum severity to show (`low`, `medium`, `high`) |
| `vueUiUxAnalyzer.pythonPath` | `python` | Path to Python interpreter |
| `vueUiUxAnalyzer.scanOnOpen` | `false` | Scan files when opened |
| `vueUiUxAnalyzer.ignoredRules` | `[]` | Rule IDs to suppress |

## Rules

| Rule ID | Severity | Category | Description |
|---|---|---|---|
| `missing-alt-tag` | High | Accessibility | `<img>` without `alt` attribute |
| `missing-aria-label` | High | Accessibility | Buttons/links/inputs without accessible labels |
| `low-contrast` | High | Accessibility | Color contrast below WCAG AA 4.5:1 ratio |
| `missing-viewport` | High | Responsive | HTML files missing viewport meta tag |
| `missing-lang-attribute` | Medium | Accessibility | `<html>` missing `lang` attribute |
| `non-semantic-tag` | Medium | Semantics | `<div>` used where `<nav>`, `<header>`, etc. should be |
| `heading-hierarchy` | Medium | Semantics | Skipped heading levels (h1 → h3) |
| `inline-style-overuse` | Medium | Style | Excessive inline styles |
| `non-responsive-layout` | Medium | Responsive | Fixed pixel widths on containers |
| `missing-scoped-style` | Medium | Vue | Unscoped `<style>` blocks in components |
| `small-clickable-area` | Medium | Accessibility | Touch targets below 44×44px minimum |
| `font-inconsistency` | Low | Style | More than 3 font families in a file |
| `missing-component-name` | Low | Vue | Components without explicit `name` option |
| `large-template` | Low | Vue | Templates exceeding 150 lines or 50 elements |

## Architecture

```
vue-uiux-analyzer/
├── src/                    # TypeScript (VS Code extension glue)
│   ├── extension.ts        # Entry point, commands, events
│   ├── providers.ts        # Diagnostics + Quick Fix code actions
│   ├── dashboard.ts        # Webview panel manager
│   └── pythonEngine.ts     # Bridge to Python backend
├── python/                 # Python (analysis engine)
│   ├── cli.py              # CLI entry point (JSON protocol)
│   ├── scanner_engine.py   # File discovery + orchestration
│   ├── rule_engine.py      # Rule management
│   ├── fix_engine.py       # Fix application
│   ├── cache_manager.py    # MD5-based caching
│   ├── scan_history.py     # Persistent history
│   ├── vue_parser.py       # Vue SFC parser
│   └── rules/              # Modular rule implementations
├── resources/
│   ├── dashboard.html      # Vue 3 webview dashboard
│   └── icon.svg            # Activity bar icon
└── test-vue-project/       # Sample project for testing
```

## License

MIT
