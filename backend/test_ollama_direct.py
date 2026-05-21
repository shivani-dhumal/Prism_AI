import requests
import json
import time

url = "http://localhost:11434/api/generate"
payload = {
    "model": "gemma3:12b",
    "prompt": "Say hello in exactly 3 words.",
    "stream": False
}

print("Sending request to Ollama...")
start = time.time()
try:
    response = requests.post(url, json=payload, timeout=60)
    elapsed = time.time() - start
    print(f"Elapsed: {elapsed:.2f}s")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json().get('response')}")
except Exception as e:
    print(f"Error after {time.time() - start:.2f}s: {e}")
