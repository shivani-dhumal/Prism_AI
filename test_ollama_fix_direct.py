import requests
import json
import time

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma3:12b"

# Construct a real prompt for academicYears.js
prompt = """You are a code fixer. Fix the bug and return the COMPLETE replacement for the provided code block.

BUG TITLE: State variables initialized as empty objects
BUG LINE IN FILE: 12
BUG LINE INSIDE BLOCK: 12
BUG DESCRIPTION: State variables are initialized as empty objects which might lead to errors if properties are accessed before being populated.
SUGGESTED FIX: Initialize state variables with proper default properties.

CODE BLOCK TO REPLACE (60 lines, no line numbers):
```js
const state = {
  academicYears: {},
  currentAcademicYear: {}
};

const getters = {
  academicYears: state => state.academicYears,
  currentAcademicYear: state => state.currentAcademicYear
};
```

REQUIREMENTS:
1. Return the COMPLETE replacement block, not a snippet.
2. Keep unrelated lines exactly the same.
3. Preserve indentation and formatting.
4. Do not include line numbers.
5. Return only code in one fenced code block.
"""

print("Sending direct fix request to Ollama...")
start = time.time()
try:
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "temperature": 0.1,
        },
        timeout=180
    )
    elapsed = time.time() - start
    print(f"Status Code: {response.status_code}")
    print(f"Elapsed: {elapsed:.2f}s")
    if response.status_code == 200:
        data = response.json()
        print("Response received:")
        print(data.get("response", ""))
    else:
        print(response.text)
except Exception as e:
    print(f"Error: {e}")
