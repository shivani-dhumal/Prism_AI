# PrismAI Code Analyzer

A VS Code extension that integrates **PrismAI** forensic code analysis directly into your editor.

## Features

- **Dashboard** – View analysis summary and navigate to tools
- **Architecture Map** – Visualize codebase structure and dependencies with Cytoscape
- **Dependency Graph** – Analyze import topology and circular dependencies
- **Audit Report** – Review all findings and issues organized by severity
- **File Analysis** – Right-click any file to analyze it individually
- **Live Webviews** – All visualizations run in VS Code webview panels

## Commands

| Command | Description |
|---------|-------------|
| `PrismAI: Open Dashboard` | Open the main dashboard |
| `PrismAI: Analyze This File` | Analyze the current file (right-click or editor context) |
| `PrismAI: Show Architecture Map` | View architecture visualization |
| `PrismAI: Show Dependency Graph` | View dependency graph |
| `PrismAI: Show Audit Report` | View full audit report |

## Setup

### Prerequisites
- VS Code 1.75+
- PrismAI backend server running (default: `http://localhost:5000`)

### Installation

1. Clone or download this extension folder
2. Install dependencies:
   ```bash
   npm install
   ```
3. Compile TypeScript:
   ```bash
   npm run compile
   ```
4. Open the extension folder in VS Code and press `F5` to start debugging

### Configuration

Edit VS Code settings to configure the extension:

```json
{
  "prismia.serverUrl": "http://localhost:5000",
  "prismia.autoAnalyze": false
}
```

## Development

### File Structure

```
vscode-extension/
├── src/
│   └── extension.ts       # Main extension code
├── package.json           # Extension manifest
├── tsconfig.json          # TypeScript config
└── README.md             # This file
```

### Build & Run

- **Compile**: `npm run compile`
- **Watch mode**: `npm run watch`
- **Debug**: Press `F5` in VS Code
- **Package**: `vsce package`

## Architecture

The extension communicates with the PrismAI backend server via HTTP:

- **Dashboard** → `GET /api/dashboard-data`
- **Architecture** → `GET /api/architecture`
- **Dependencies** → `GET /api/dependencies`
- **Audit** → `GET /api/audit-report`
- **File Analysis** → `POST /api/analyze-file`

Webviews display data using Vue 3 and Cytoscape.js for visualizations.

## License

MIT
