import requests
import os

url = "http://localhost:5000/api/bugs/244/ai-fix"
file_path = r"C:\Users\shivanid\Desktop\ShivaniD\StudentLogin\client\app\src\store\modules\academicYears.js"

try:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    print(f"File content read, size: {len(content)} characters.")
    payload = {
        "file_content": content,
        "file_path": file_path
    }
    
    response = requests.post(url, json=payload, timeout=30)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
