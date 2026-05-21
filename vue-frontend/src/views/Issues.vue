<template>
  <div>
    <!-- Header -->
    <section class="issues-top">
      <div>
        <h1>Code Issues &amp; Fixes</h1>
        <p>Review issues from the project you scanned, generate fixes, and compare previous code with fixed code.</p>
      </div>
      <div class="project-chip" id="projectChip">{{ projectLabel }}</div>
    </section>

    <!-- Issues list -->
    <div class="issues-container">
      <div v-if="loading" class="empty-state">
        <i class="fas fa-spinner" style="animation:spin .8s linear infinite;"></i> Loading issues...
      </div>
      <div v-else-if="!issues.length" class="empty-state">No issues found for the current scanned project.</div>
      <div
        v-for="issue in issues"
        :key="issue.id"
        class="issue-card"
      >
        <div class="issue-header">
          <span :class="`badge badge-${(issue.severity||'MEDIUM').toLowerCase()}`">{{ issue.severity || 'MEDIUM' }}</span>
          <div class="issue-title">{{ issue.title || 'Issue' }}</div>
        </div>
        <div class="issue-desc">{{ issue.description || '' }}</div>
        <div class="issue-meta">
          <span class="issue-path" :title="issue.file_path">
            <i class="fas fa-file"></i> {{ shortPath(issue.file_path || issue.file_name || '') }}
          </span>
          <span><i class="fas fa-code"></i> Line {{ issue.line_number || 1 }}</span>
          <span><span class="badge badge-info">{{ issue.status || 'OPEN' }}</span></span>
        </div>
        <div class="issue-actions">
          <button class="btn btn-primary" @click="showFix(issue)">
            <i class="fas fa-code-compare"></i> Fix
          </button>
          <button class="btn btn-secondary" @click="askChatbot(issue)">
            <i class="fas fa-lightbulb"></i> Reason
          </button>
          <button class="btn btn-danger" @click="ignoreIssue(issue.id)">
            <i class="fas fa-eye-slash"></i> Ignore
          </button>
        </div>
      </div>
    </div>

    <!-- Fix Modal -->
    <Teleport to="body">
      <div class="fix-modal-overlay" v-if="fixModal" @click.self="fixModal = false">
        <div class="fix-modal">
          <div class="fix-modal-header">
            <div style="min-width:0;">
              <h3>{{ currentIssue?.title || 'Fix Issue' }}</h3>
              <div class="fix-subtitle">{{ currentIssue?.file_path || '' }} | line {{ currentIssue?.line_number || 1 }}</div>
            </div>
            <button class="fix-modal-close" @click="fixModal = false">&times;</button>
          </div>
          <div class="reason-panel" v-html="reasonText"></div>
          <div class="fix-modal-body">
            <div class="code-section original">
              <div class="code-header">
                <span><i class="fas fa-file-code"></i> Previous Code</span>
                <span>{{ originalRange }}</span>
              </div>
              <pre class="code-block" v-html="originalHtml"></pre>
            </div>
            <div class="code-section fixed">
              <div class="code-header">
                <span><i class="fas fa-wand-magic-sparkles"></i> Fixed Code</span>
                <span>{{ fixedRange }}</span>
              </div>
              <pre class="code-block" v-html="fixedHtml"></pre>
            </div>
          </div>
          <div class="fix-modal-footer">
            <div class="footer-left">
              <button class="btn btn-secondary" @click="askChatbot(currentIssue)"><i class="fas fa-comments"></i> Ask Chatbot Why</button>
              <button class="btn btn-secondary" :disabled="generating" @click="generateFix">
                <i v-if="!generating" class="fas fa-magic"></i>
                <span v-else class="spinner"></span>
                {{ generating ? 'Generating...' : 'Generate Fix' }}
              </button>
            </div>
            <div class="footer-right">
              <button class="btn btn-secondary" @click="fixModal = false">Close</button>
              <button v-if="showApply" class="btn btn-primary" @click="applyFix">
                <i class="fas fa-check"></i> Apply Fix
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { API } from '../api.js'

const router = useRouter()

const issues = ref([])
const loading = ref(true)
const projectLabel = ref('Loading project...')

// Fix modal state
const fixModal = ref(false)
const currentIssue = ref(null)
const originalCode = ref('')
const fixedCode = ref('')
const originalRange = ref('')
const fixedRange = ref('')
const generating = ref(false)
const showApply = ref(false)
let lineStart = 1, lineEnd = 1

const escapeHtml = (t) =>
  String(t ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]))

const shortPath = (p, max = 110) => {
  p = String(p || '')
  return p.length > max ? '...' + p.slice(-max + 3) : p
}

const isDatabaseIssue = (issue) => issue && /^\d+$/.test(String(issue?.id))

function renderCode(code, start, compare = '') {
  const lines = String(code || '').split('\n')
  const cmp = String(compare || '').split('\n')
  return lines.map((line, i) => {
    const changed = compare && line !== (cmp[i] ?? '')
    return `<span class="code-line"><span class="line-num">${start + i}</span><span class="line-code${changed ? ' changed' : ''}">${escapeHtml(line || ' ')}</span></span>`
  }).join('')
}

const originalHtml = computed(() => renderCode(originalCode.value, lineStart))
const fixedHtml = computed(() => renderCode(fixedCode.value, lineStart, originalCode.value))

const reasonText = computed(() => {
  if (!currentIssue.value) return 'Select an issue to review the reason and generate a fix.'
  return `<strong>Reason:</strong> ${escapeHtml(currentIssue.value.description || 'No description available.')}<br><strong>Suggested direction:</strong> ${escapeHtml(currentIssue.value.fix_suggestion || 'Generate a fix to get a concrete repair plan.')}`
})

onMounted(async () => {
  try {
    const project = await API.currentProject()
    projectLabel.value = `${project.project_name}: ${project.project_root}`
  } catch {
    projectLabel.value = 'Current scanned project'
  }
  await loadIssues()
})

async function loadIssues() {
  loading.value = true
  try {
    issues.value = await API.allBugs() || []
  } catch (e) {
    console.error(e)
    issues.value = []
  } finally {
    loading.value = false
  }
}

async function showFix(issue) {
  currentIssue.value = issue
  fixedCode.value = issue.fixed_code || ''
  originalCode.value = ''
  originalRange.value = ''
  fixedRange.value = ''
  showApply.value = false
  const lineNum = Math.max(1, parseInt(String(issue.line_number || '1').match(/\d+/)?.[0] ?? '1', 10))
  lineStart = Math.max(1, lineNum - 8)
  lineEnd = lineNum + 8
  fixModal.value = true

  try {
    const content = await API.fileContent(issue.file_path)
    const fullContent = content.content || ''
    const lines = fullContent.split('\n')
    lineStart = Math.max(1, lineNum - 8)
    lineEnd = Math.min(lines.length, lineNum + 8)
    originalCode.value = lines.slice(lineStart - 1, lineEnd).join('\n')
    originalRange.value = `Lines ${lineStart}-${lineEnd}`
    if (fixedCode.value) {
      fixedRange.value = 'Saved fix'
      showApply.value = isDatabaseIssue(issue)
    }
  } catch (e) {
    originalCode.value = 'Could not load source code: ' + e.message
  }
}

async function generateFix() {
  if (!currentIssue.value) return
  generating.value = true
  fixedCode.value = 'Generating fixed code...'
  try {
    if (!isDatabaseIssue(currentIssue.value)) {
      const prompt = [
        'Create a focused fixed-code preview for this UI/accessibility issue.',
        `Issue: ${currentIssue.value.title || ''}`,
        `Severity: ${currentIssue.value.severity || ''}`,
        `File: ${currentIssue.value.file_path || ''}`,
        `Line: ${currentIssue.value.line_number || ''}`,
        `Description: ${currentIssue.value.description || ''}`,
        `Suggested Fix: ${currentIssue.value.fix_suggestion || ''}`,
        '',
        'Previous code:',
        originalCode.value || '(source code was not available)',
        '',
        'Return the corrected code block and briefly explain why it fixes the issue.',
      ].join('\n')
      const res = await API.ollamaChat({ message: prompt })
      fixedCode.value = res.response || 'No fix returned.'
      fixedRange.value = 'Fix preview'
      showApply.value = false
      return
    }
    const fullFile = await API.fileContent(currentIssue.value.file_path)
    const result = await API.aiFix(currentIssue.value.id, {
      file_content: fullFile.content || originalCode.value,
      title: currentIssue.value.title,
      description: currentIssue.value.description,
      fix_suggestion: currentIssue.value.fix_suggestion,
      severity: currentIssue.value.severity,
      line_number: currentIssue.value.line_number,
      file_path: currentIssue.value.file_path,
    })
    fixedCode.value = result.fixed_code || ''
    lineStart = result.line_start || lineStart
    lineEnd = result.line_end || lineEnd
    originalCode.value = result.original_code || originalCode.value
    originalRange.value = `Lines ${lineStart}-${lineEnd}`
    fixedRange.value = result.can_apply === false ? 'Preview only' : 'AI replacement'
    showApply.value = result.can_apply !== false
  } catch (e) {
    fixedCode.value = 'Fix generation failed: ' + e.message
  } finally {
    generating.value = false
  }
}

async function applyFix() {
  if (!currentIssue.value || !fixedCode.value) return
  try {
    await API.applyFix(currentIssue.value.id, {
      fixed_code: fixedCode.value,
      file_path: currentIssue.value.file_path,
      line_start: lineStart,
      line_end: lineEnd,
    })
    fixModal.value = false
    await loadIssues()
  } catch (e) {
    alert('Error applying fix: ' + e.message)
  }
}

function askChatbot(issue) {
  if (!issue) return
  const context = [
    `Issue: ${issue.title || 'Issue'}`,
    `Severity: ${issue.severity || ''}`,
    `File: ${issue.file_path || ''}`,
    `Line: ${issue.line_number || ''}`,
    `Description: ${issue.description || ''}`,
    `Suggested Fix: ${issue.fix_suggestion || ''}`,
    '', 'Previous Code:',
    originalCode.value || '(Open the fix modal to load source context.)',
    '', 'Fixed Code:',
    fixedCode.value || '(No fixed code generated yet.)',
    '', 'Question: Tell me the reason for this issue, why the fix works, and what could happen if I do not fix it.',
  ].join('\n')
  router.push(`/chatbot?context=${encodeURIComponent(context)}`)
}

async function ignoreIssue(id) {
  if (!confirm('Mark this issue as ignored?')) return
  try {
    await API.updateBugStatus(id, 'IGNORED', null)
    await loadIssues()
  } catch (e) {
    alert('Error: ' + e.message)
  }
}
</script>

<style scoped>
.issues-top { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; margin-bottom:24px; flex-wrap:wrap; }
.project-chip { color:var(--text-2); font-family:var(--f-mono); font-size:12px; background:var(--bg-alt); border:1px solid var(--border); border-radius:var(--radius-md); padding:9px 12px; max-width:720px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.issues-container { display:grid; grid-template-columns:1fr; gap:14px; }
.issue-card { background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-lg); padding:18px; transition:border-color .2s ease,box-shadow .2s ease; }
.issue-card:hover { border-color:var(--accent); box-shadow:var(--shadow-sm); }
.issue-header { display:flex; align-items:flex-start; gap:12px; margin-bottom:10px; }
.issue-title { font-weight:700; color:var(--text); flex:1; line-height:1.35; }
.issue-desc { font-size:13px; color:var(--text-2); margin-bottom:12px; line-height:1.55; }
.issue-meta { display:flex; gap:10px; flex-wrap:wrap; align-items:center; font-size:12px; color:var(--text-2); margin-bottom:12px; }
.issue-path { font-family:var(--f-mono); max-width:720px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.issue-actions { display:flex; gap:8px; flex-wrap:wrap; }
.issue-actions .btn { padding:7px 12px; font-size:12px; }
/* Fix modal */
.fix-modal-overlay { position:fixed; inset:0; background:rgba(15,23,42,.68); display:flex; align-items:center; justify-content:center; z-index:300; padding:22px; }
.fix-modal { background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-lg); width:min(1180px,96vw); max-height:92vh; display:flex; flex-direction:column; box-shadow:var(--shadow-lg); }
.fix-modal-header { padding:18px 22px; border-bottom:1px solid var(--border); background:var(--bg-alt); display:flex; justify-content:space-between; gap:16px; }
.fix-modal-header h3 { margin:0; font-size:18px; }
.fix-subtitle { color:var(--text-2); font-size:12px; margin-top:5px; font-family:var(--f-mono); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:860px; }
.fix-modal-close { background:none; border:0; font-size:24px; cursor:pointer; color:var(--text-2); }
.reason-panel { margin:18px 22px 0; padding:14px 16px; border:1px solid var(--border); border-radius:var(--radius-md); background:var(--bg-alt); color:var(--text-2); font-size:13px; line-height:1.55; }
.fix-modal-body { flex:1; overflow:auto; padding:18px 22px; display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.code-section { border:1px solid var(--border); border-radius:var(--radius-md); overflow:hidden; background:var(--bg); min-width:0; }
.code-header { padding:10px 13px; border-bottom:1px solid var(--border); background:var(--bg-alt); font-weight:800; font-size:12px; text-transform:uppercase; letter-spacing:.05em; display:flex; justify-content:space-between; gap:10px; }
.code-block { margin:0; padding:0; overflow:auto; max-height:52vh; background:var(--bg); }
.code-block :deep(.code-line) { display:grid; grid-template-columns:48px 1fr; min-width:max-content; font-family:var(--f-mono); font-size:12px; line-height:1.55; }
.code-block :deep(.line-num) { color:var(--text-3); text-align:right; padding:0 10px; user-select:none; border-right:1px solid var(--border); background:var(--bg-alt); }
.code-block :deep(.line-code) { padding:0 12px; white-space:pre; color:var(--text); }
.code-section.original .code-block :deep(.line-code.changed) { background:rgba(239,68,68,.10); }
.code-section.fixed .code-block :deep(.line-code.changed) { background:rgba(16,185,129,.12); }
.fix-modal-footer { padding:14px 22px; border-top:1px solid var(--border); background:var(--bg-alt); display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.footer-left,.footer-right { display:flex; gap:8px; flex-wrap:wrap; }
@media (max-width:900px) { .fix-modal-body { grid-template-columns:1fr; } }
</style>
