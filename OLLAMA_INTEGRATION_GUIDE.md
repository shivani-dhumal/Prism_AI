# PrismAI + Ollama Integration Guide

**Date**: May 19, 2026  
**Status**: ✅ **OLLAMA (GEMMA 3:12B) FULLY INTEGRATED**

---

## 📋 Overview

Your PrismAI application now uses **local Ollama with Gemma 3:12B** for all AI features:
- ✅ Bug detection during scans
- ✅ Fix code generation
- ✅ AI chatbot responses
- ✅ Dependency analysis explanations

**No API keys needed. Everything runs locally on your machine.**

---

## 🚀 Quick Start

### Step 1: Ensure Ollama is Running

Make sure Ollama is started with Gemma 3:12B model:

```powershell
# Start Ollama service
ollama serve

# In another terminal, pull Gemma 3:12B (if not already done)
ollama pull gemma3:12b
```

Verify Ollama is running at `http://localhost:11434`:
```powershell
curl http://localhost:11434/api/tags
```

### Step 2: Start PrismAI

```powershell
cd "c:\Users\shivanid\Desktop\folder analysyis"
python app.py
```

Open browser: **http://localhost:5000**

---

## 🔄 Complete Workflow

### **Workflow: Scan → Issues → Generate Fix → Explain**

#### **Step 1: Start a Scan**
1. Go to **Dashboard** (http://localhost:5000/)
2. Click **"Start New Analysis"**
3. Enter folder path: `C:\Users\shivanid\Desktop\[YourProject]`
4. Click **"Analyze"**
5. **Wait for scan to complete** (progress bar shows 0-100%)
   - File discovery: 0-40%
   - Ollama analysis: 40-100% (scans each file with Gemma 3:12B)

#### **Step 2: View Issues**
1. Go to **Issues** page (http://localhost:5000/issues)
2. See all bugs found with:
   - Severity badge (CRITICAL/HIGH/MEDIUM/LOW)
   - Issue title and description
   - File name and line number

#### **Step 3: View & Generate Fix**
1. Click **"View Fix"** button on any issue
2. See **Original Code** (extracted from file around the bug)
3. Two options:
   - **If fix already exists**: See side-by-side **Original Code vs Fixed Code**
   - **If fix doesn't exist**: Click **"Generate Fix"** button
4. Ollama (Gemma 3:12B) generates the fix

#### **Step 4: Apply Fix**
1. After fix is generated, review the comparison
2. Click **"Apply Fix"** to automatically update the source file
3. Fix is saved to database and applied to file

#### **Step 5: Ask Chatbot Why**
1. In the fix modal, click **"Ask Chatbot Why"**
2. Opens chatbot with full issue context
3. **Automatically asks**: "Tell me the reason for this issue, why the fixed code works, and what could happen if I do not fix it."
4. Gemma 3:12B responds with:
   - Root cause of the bug
   - Why the fix works
   - Consequences of not fixing it
   - Security implications (if applicable)

---

## 🏗️ Architecture

### What Changed

| Component | Before | After |
|-----------|--------|-------|
| **Scan Analysis** | Gemini API (cloud) | Ollama Gemma 3:12B (local) |
| **Fix Generation** | Gemini API (cloud) | Ollama Gemma 3:12B (local) |
| **Chatbot** | Ollama (local) | Ollama (local) ✓ |
| **Dependencies** | Ollama (local) | Ollama (local) ✓ |

### Files Modified

1. **`scanners/ollama_bug_detector.py`** (NEW)
   - Replaces `gemini_bug_detector.py`
   - Uses local Ollama API: `http://localhost:11434/api/generate`
   - Model: `gemma3:12b`
   - Same bug detection logic, JSON format

2. **`app.py`** (UPDATED)
   - Line ~589: Import `ollama_bug_detector` instead of `gemini_bug_detector`
   - Line ~1317: `/api/bugs/<id>/ai-fix` endpoint now calls Ollama
   - Added: `import requests` for Ollama API calls

3. **`templates/issues.html`** (ENHANCED)
   - "Generate Fix" button for on-demand fix creation
   - "Ask Chatbot Why" button that redirects to chatbot with context
   - Side-by-side code comparison (original vs fixed)
   - Better UI with line numbers and syntax highlighting

4. **`templates/chatbot.html`** (ENHANCED)
   - Auto-detects issue context vs dependency context
   - Auto-sends explanation request for issue context
   - Displays issue details before asking for explanation

---

## 🔌 Ollama API Endpoints Used

### 1. Bug Detection (Scan)
```
POST http://localhost:11434/api/generate
{
  "model": "gemma3:12b",
  "prompt": "[BUG_DETECT_PROMPT]",
  "stream": false,
  "temperature": 0.15
}
```
Response: JSON with `{"bugs": [...]}`

### 2. Fix Generation
```
POST http://localhost:11434/api/generate
{
  "model": "gemma3:12b",
  "prompt": "[FIX_PROMPT]",
  "stream": false,
  "temperature": 0.1
}
```
Response: JSON with `{"response": "[FIXED_CODE]"}`

### 3. Chat
```
POST http://localhost:11434/api/chat
{
  "model": "gemma3:12b",
  "messages": [{"role": "user", "content": "..."}]
}
```
Response: JSON with `{"response": "[ANSWER]"}`

---

## ⚙️ Configuration

### Ollama URL
- **Default**: `http://localhost:11434`
- **To change**: Edit `scanners/ollama_bug_detector.py` line 38
- **To change**: Edit `app.py` in `generate_ai_fix()` function

### Model Name
- **Default**: `gemma3:12b`
- **To use different model**: Update in both files above
- **Available models**: Run `ollama list` to see installed models

### Timeouts
- **Scan timeout**: 30 minutes (per scan)
- **Ollama request timeout**: 120 seconds (per file)
- Can be adjusted in `app.py` line 548 and `scanners/ollama_bug_detector.py` line 108

---

## 🐛 Troubleshooting

### Error: "Cannot connect to Ollama at http://localhost:11434"

**Solution**: Make sure Ollama is running
```powershell
# Check if Ollama service is running
ollama serve

# Or use the Ollama app directly
```

### Error: "gemma3:12b model not found"

**Solution**: Pull the model
```powershell
ollama pull gemma3:12b
```

### Scan is slow or times out

**Reason**: Ollama processes each file sequentially (may take 5-10 seconds per file)

**Solutions**:
1. Increase timeout in `app.py` line 548: Change `SCAN_TIMEOUT = 1800` to `3600` (60 min)
2. Use a faster model: `ollama pull phi:latest` (faster but less accurate)
3. Scan fewer files: Focus on specific directories

### Chatbot response is empty or wrong

**Solution**: Ollama may be overloaded
1. Restart Ollama: `ollama serve` (stop and restart)
2. Check Ollama logs for errors
3. Try again after a few seconds

---

## 📊 Performance Expectations

### Local Ollama (Gemma 3:12B)

| Operation | Time | Notes |
|-----------|------|-------|
| Bug Detection per file | 3-10 seconds | Depends on file size & system CPU/GPU |
| Fix Generation | 5-15 seconds | Depends on code context size |
| Chat Response | 3-8 seconds | First response may be slower |
| Full Scan (10 files) | 5-10 minutes | Sequential processing |

**Factors affecting speed**:
- CPU/GPU: GPU is much faster (30x faster than CPU)
- File size: Larger files take longer
- System RAM: More RAM = faster processing
- Other processes: Close resource-intensive apps

---

## ✨ Features Now Available

### Complete Issue Workflow
- ✅ Scan projects for bugs using Ollama
- ✅ View all issues with severity levels
- ✅ Generate AI fixes on-demand
- ✅ View original vs fixed code side-by-side
- ✅ Apply fixes directly to source files
- ✅ Ask chatbot why an issue occurs
- ✅ Understand consequences of not fixing

### AI Explanations
- ✅ Bug root cause analysis
- ✅ Security implications
- ✅ Performance impact
- ✅ Refactoring suggestions
- ✅ Code quality improvements

### Local Processing
- ✅ No API keys required
- ✅ No cloud dependencies
- ✅ All data stays on your machine
- ✅ Works offline after model is downloaded
- ✅ No rate limits or quotas

---

## 🔐 Privacy & Security

✅ **All processing happens locally**
- Code files never leave your machine
- No data sent to any cloud service
- No API keys or credentials needed
- Database stored locally

---

## 📝 API Endpoints

### GET `/api/file/content?path=[filepath]`
Returns file content with line numbers

### GET `/api/file/annotations?path=[filepath]`
Returns line-by-line bug annotations

### POST `/api/bugs/<id>/ai-fix`
Generate AI fix for a bug
- Input: `file_content`, `title`, `description`, `fix_suggestion`, `severity`, `line_number`
- Output: `fixed_code`, `original_code`, `line_start`, `line_end`, `can_apply`

### POST `/api/bugs/<id>/apply-fix`
Apply generated fix to source file
- Input: `fixed_code`, `file_path`, `line_start`, `line_end`
- Output: `success`, `message`

### POST `/api/ollama/chat`
Send message to Ollama chatbot
- Input: `message`
- Output: `response`, `model`

---

## 🚀 Next Steps (Optional)

1. **Use a faster model**:
   ```powershell
   ollama pull phi:latest
   # Update model name in both files
   ```

2. **Enable GPU acceleration**:
   - Reinstall Ollama with GPU support
   - Check: `ollama -v` should show CUDA/Metal support

3. **Batch processing** (not yet implemented):
   - Run multiple scans in parallel
   - Would require refactoring lock mechanism

4. **Custom prompts**:
   - Edit `BUG_DETECT_PROMPT` in `scanners/ollama_bug_detector.py`
   - Edit fix prompt in `app.py` function `generate_ai_fix()`

---

## ✅ Verification Checklist

- [ ] Ollama is running (`ollama serve`)
- [ ] Gemma 3:12B is installed (`ollama list`)
- [ ] Flask app is running (`python app.py`)
- [ ] Can access dashboard (http://localhost:5000)
- [ ] Can start a scan
- [ ] Scan completes and shows issues
- [ ] Can generate a fix
- [ ] Can view original vs fixed code
- [ ] Can ask chatbot why issue occurs

---

## 📞 Support

If issues occur:
1. Check Ollama is running: `curl http://localhost:11434/api/tags`
2. Check Flask logs: Look at console output
3. Check file permissions: Can PrismAI read/write the source files?
4. Check disk space: Ollama models require 5-10GB
5. Restart everything: Stop Ollama and Flask, restart both

---

**Status**: 🟢 **READY TO USE**

Your PrismAI application is now fully powered by local Ollama Gemma 3:12B!

