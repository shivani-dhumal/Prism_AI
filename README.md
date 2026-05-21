# 🔮 PrismAI — Intelligent Code Analyzer

> An AI-powered codebase analysis platform that scans, visualizes, and audits your project with Gemini AI, Ollama (local LLMs), and an interactive dependency mind map.

![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.x-black?style=for-the-badge&logo=flask)
![Gemini](https://img.shields.io/badge/Google_Gemini-AI-4285F4?style=for-the-badge&logo=google&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-Database-00758f?style=for-the-badge&logo=mysql&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-purple?style=for-the-badge)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🧠 **Dependency Mind Map** | Interactive radial mind map of all file relationships — concentric, tree, and force layouts |
| 🤖 **Gemini AI Analysis** | Bug detection, code auditing, and risk assessment powered by Google Gemini |
| 🦙 **Ollama Integration** | Local LLM (Gemma 3) for offline code review without API costs |
| 📊 **Code Metrics** | Complexity, coupling, and blast-radius scoring per file |
| 🔍 **Multi-Scanner Pipeline** | UI consistency, accessibility, API extraction, spell checking, and more |
| 💬 **AI Chatbot** | Context-aware assistant that understands your codebase |
| 📁 **File Explorer** | Visual dependency graph with click-to-inspect nodes |
| 📄 **Report Generation** | HTML audit reports, risk predictions, and component summaries |
| 🎨 **Vue UI/UX Analyzer** | Dedicated scanner for Vue.js components (accessibility, contrast, responsiveness) |

---

## 🖥️ Screenshots

### Dependency Graph + Mind Map
Click **🧠 Mind Map** to open a full-screen radial view color-coded by file type with 3 layout modes.

### AI Code Assistant
Click any file node → get instant dependency analysis + ask the AI assistant for refactoring suggestions.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- MySQL 8+
- [Ollama](https://ollama.ai) (optional, for local LLM)
- Google Gemini API key

### 1. Clone the repository

```bash
git clone https://github.com/shivani-dhumal/Prism_AI.git
cd Prism_AI
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
DB_HOST=localhost
DB_USER=your_db_user
DB_PASS=your_db_password
DB_NAME=codebase_scanner_db_2

GEMINI_API_KEY=your_gemini_api_key_here

OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=gemma3:12b
```

### 4. Set up the database

```bash
python database_setup.py
```

### 5. Run the app

```bash
python run.py
```

Or directly from the backend folder:
```bash
cd backend
python app.py
```

Open your browser at **http://localhost:5000**

---

## 🗂️ Project Structure

```
Prism_AI/
├── backend/                        # 🐍 Python / Flask server
│   ├── app.py                      # Flask main application & all API routes
│   ├── config.py                   # Configuration & environment loader
│   ├── main.py                     # Analysis pipeline entry point
│   ├── database_ops.py             # MySQL DB operations
│   ├── database_setup.py           # DB schema initialization
│   ├── ai_reasoning_engine.py      # AI chain-of-thought reasoning
│   ├── risk_model.py               # File risk scoring model
│   ├── generate_report.py          # HTML audit report generator
│   ├── dependency_visualizer.py    # Standalone dependency graph HTML
│   ├── scanners/                   # Modular scanner pipeline
│   │   ├── gemini_bug_detector.py  # Gemini AI bug detection
│   │   ├── ollama_bug_detector.py  # Local LLM bug detection
│   │   ├── ui_consistency_rules.py # UI/UX rule checking
│   │   ├── accessibility_checker.py
│   │   ├── code_metrics_scanner.py
│   │   └── ...
│   ├── code-analyzer/              # MCP-compatible analyzer module
│   ├── reports/                    # Generated scan reports (HTML/JSON)
│   └── requirements.txt
│
├── frontend/                       # 🎨 Web UI assets
│   ├── templates/                  # Flask Jinja2 HTML templates
│   │   ├── base.html               # Shared layout & navigation
│   │   ├── index.html              # Dashboard home
│   │   ├── dependency_graph.html   # Interactive graph + 🧠 Mind Map
│   │   ├── chatbot.html            # AI chat interface
│   │   ├── issues.html             # Issues browser
│   │   └── audit_report.html
│   └── static/                     # Static assets
│       ├── css/                    # Stylesheets
│       └── js/                     # JavaScript & API client
│
├── extensions/                     # 🔌 Standalone tools & extensions
│   ├── vscode-extension/           # VSCode extension
│   └── gemini-chatbot/             # Standalone Gemini chatbot
│
├── vue-uiux-analyzer/              # 🟢 Vue.js UI/UX Analyzer (VSCode ext.)
│
├── run.py                          # ▶ Start app from project root
├── .env.example                    # Environment template (copy to .env)
├── .gitignore
└── README.md
```

---

## 🧠 Dependency Mind Map

Navigate to **Code Structure** in the sidebar, then click the purple **🧠 Mind Map** button.

| Layout | Description |
|---|---|
| **Concentric** | Nodes arranged in rings by connection degree (most connected = center) |
| **Tree** | Hierarchical breadth-first tree layout |
| **Force** | Physics-based force-directed simulation |

- Hover a node → connected edges highlight in amber
- Click a node → closes mind map, focuses that file in the main graph

---

## 🔧 Key Modules

### Scanners
- **`gemini_bug_detector.py`** — Sends code to Gemini API for bug analysis
- **`llm_scanner.py`** — Ollama-based local LLM scanning
- **`ui_consistency_rules.py`** — CSS/HTML consistency checks
- **`accessibility_checker.py`** — WCAG accessibility rule evaluation
- **`code_metrics_scanner.py`** — Cyclomatic complexity, LOC, coupling

### AI Engine
- **`ai_reasoning_engine.py`** — Chain-of-thought reasoning for code issues
- **`risk_model.py`** — ML-style risk scoring per file

### Reports
- **`generate_report.py`** — Full HTML audit dashboard
- **`ollama_report_generator.py`** — Local LLM report generation

---

## 🛡️ Security

- `.env` is **never committed** — use `.env.example` as a template
- API keys stay local
- Database credentials are environment-variable only

---

## 📦 Requirements

See [`requirements.txt`](requirements.txt) for the full list. Key dependencies:

```
flask
python-dotenv
mysql-connector-python
google-generativeai
requests
beautifulsoup4
pyspellchecker
```

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit changes: `git commit -m "Add your feature"`
4. Push: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License.

---

## 👩‍💻 Author

**Shivani Dhumal**  
[![GitHub](https://img.shields.io/badge/GitHub-shivani--dhumal-black?style=flat&logo=github)](https://github.com/shivani-dhumal)
