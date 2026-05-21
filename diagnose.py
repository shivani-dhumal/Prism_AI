import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("PROJECT DIAGNOSTIC REPORT")
print("=" * 60)

errors = []

# Test 1: DB connection
try:
    from database_ops import get_db
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM scans")
    scan_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM files")
    file_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM bug_detections")
    bug_count = cur.fetchone()[0]
    cur.execute("SELECT id, status, current_stage, progress FROM scans ORDER BY id DESC LIMIT 5")
    scans = cur.fetchall()
    cur.close()
    conn.close()
    print(f"[OK] DB connected — scans:{scan_count}, files:{file_count}, bugs:{bug_count}")
    print(f"     Recent scans: {scans}")
except Exception as e:
    print(f"[FAIL] DB: {e}")
    errors.append(f"DB: {e}")

# Test 2: Gemini import
try:
    from google import genai
    from config import GEMINI_API_KEY
    print(f"[OK] google-genai import — API key: {'SET' if GEMINI_API_KEY else 'MISSING'}")
except Exception as e:
    print(f"[FAIL] google-genai: {e}")
    errors.append(f"google-genai: {e}")

# Test 3: Ollama reachable
try:
    import requests
    r = requests.get("http://localhost:11434/api/tags", timeout=5)
    models = [m["name"] for m in r.json().get("models", [])]
    print(f"[OK] Ollama reachable — models: {models}")
except Exception as e:
    print(f"[FAIL] Ollama: {e}")
    errors.append(f"Ollama: {e}")

# Test 4: templates
tdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
needed = ["index.html", "code_viewer.html", "chatbot.html", "issues.html",
          "audit_report.html", "architecture.html", "dependency_graph.html"]
for t in needed:
    path = os.path.join(tdir, t)
    status = "OK" if os.path.exists(path) else "MISSING"
    print(f"[{status}] template: {t}")
    if status == "MISSING":
        errors.append(f"Missing template: {t}")

# Test 5: static folder
sdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
print(f"[{'OK' if os.path.isdir(sdir) else 'MISSING'}] static/ folder")

# Test 6: scanner imports
try:
    from scanners.ollama_bug_detector import run_bug_detection
    print("[OK] ollama_bug_detector import")
except Exception as e:
    print(f"[FAIL] ollama_bug_detector: {e}")
    errors.append(f"ollama_bug_detector: {e}")

try:
    from scanners.gemini_bug_detector import run_bug_detection as gb
    print("[OK] gemini_bug_detector import")
except Exception as e:
    print(f"[FAIL] gemini_bug_detector: {e}")
    errors.append(f"gemini_bug_detector: {e}")

# Test 7: main pipeline
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "prisma_main",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "code-analyzer", "analyzer", "main.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print(f"[OK] code-analyzer/analyzer/main.py loaded — run_pipeline: {'YES' if hasattr(mod,'run_pipeline') else 'NO'}")
except Exception as e:
    print(f"[FAIL] code-analyzer/analyzer/main.py: {e}")
    errors.append(f"analyzer/main.py: {e}")

# Test 8: config
try:
    from config import TARGET_DIRECTORY, OLLAMA_URL, OLLAMA_MODEL
    target_exists = os.path.isdir(TARGET_DIRECTORY)
    print(f"[{'OK' if target_exists else 'WARN'}] TARGET_DIRECTORY: {TARGET_DIRECTORY} ({'exists' if target_exists else 'NOT FOUND'})")
    print(f"[INFO] OLLAMA_URL={OLLAMA_URL}, OLLAMA_MODEL={OLLAMA_MODEL}")
except Exception as e:
    print(f"[FAIL] config: {e}")
    errors.append(f"config: {e}")

print()
print("=" * 60)
if errors:
    print(f"FAILURES ({len(errors)}):")
    for e in errors:
        print(f"  - {e}")
else:
    print("All checks PASSED")
print("=" * 60)
