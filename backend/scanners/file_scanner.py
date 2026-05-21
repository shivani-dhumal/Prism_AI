# scanners/file_scanner.py
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_ops import save_file

def scan_file(folder_id, file_name, root_path):
    
    file_path = os.path.join(root_path, file_name)
    ext = file_name.split('.')[-1]
    
    # Save to DB
    file_id = save_file(folder_id, file_name, file_path, ext)
    
    # Read Content
    content = ""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_name}: {e}")
        
    return file_id, content, ext