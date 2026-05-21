
import os

# Load .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    # .env lives in the project root (one level above backend/)
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, '.env'))
except ImportError:
    pass

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASS', 'shivani'),
    'database': os.environ.get('DB_NAME', 'codebase_scanner_db_2')
}

TARGET_DIRECTORY = os.environ.get(
    'TARGET_DIRECTORY',
    r"C:\Users\shivanid\Desktop\ShivaniD\StudentLogin\client\app\src"
)

# Folders we NEVER want to scan
IGNORED_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "__pycache__",
    ".idea",
    ".vscode"
}

OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'gemma3:12b')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
