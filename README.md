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

### 5. Run the app

#### Option A: Running Production Build (Served via Flask)
First compile the client SPA assets:
```bash
cd vue-frontend
npm install
npm run build
cd ..
```
Then start the Flask server:
```bash
python backend/app.py
```
Open your browser at **http://localhost:5000**

#### Option B: Running Development Server (Vite Hot-Reload)
Start the Flask backend (to handle API endpoints):
```bash
python backend/app.py
```
In a new terminal, start the Vite server:
```bash
cd vue-frontend
npm run dev
```
Open your browser at **http://localhost:5173**

---

## 🗂️ Project Structure

```
Prism_AI/
├── backend/                        # 🐍 Python / Flask server
│   ├── app.py                      # Flask app, APIs & SPA routes
│   ├── config.py                   # Configuration & env variables
│   ├── main.py                     # Analysis pipeline execution
│   ├── database_ops.py             # DB operations
│   ├── scanners/                   # Core scanner scripts
│   └── ...
│
├── vue-frontend/                   # 🟢 Modern Vue 3 SPA + Vite source
│   ├── src/
│   │   ├── views/                  # Dashboard, Issues, Chatbot, Graphs
│   │   ├── api.js                  # Axios client module
│   │   ├── main.js                 # App mounting & router config
│   │   └── App.vue                 # Base layouts & theme toggling
│   ├── vite.config.js              # Vite server & proxy configurations
│   └── package.json
│
├── frontend/
│   └── dist/                       # 📦 Production compiled Vue assets (served by Flask)
│
├── extensions/                     # 🔌 Standalone extensions
├── vue-uiux-analyzer/              # 🟢 VS Code UI/UX Scanning Tool
├── run.py                          # ▶ Root entry utility
├── .env.example                    # Env config template
├── .gitignore
└── README.md
```
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
