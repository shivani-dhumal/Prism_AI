# scanners/folder_scanner.py
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_ops import save_folder

def scan_folders(root_path):
    folder_name = os.path.basename(root_path)
    return save_folder(folder_name, root_path)