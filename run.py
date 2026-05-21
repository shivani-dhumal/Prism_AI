"""
run.py — Start PrismAI from the project root.
Usage: python run.py
"""
import sys
import os

# Add backend/ to Python path so all imports resolve correctly
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

from app import app

if __name__ == '__main__':
    print("Starting PrismAI Code Analyzer...")
    print("Open: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
