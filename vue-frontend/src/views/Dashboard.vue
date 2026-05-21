<template>
  <div>
    <!-- Hero -->
    <section class="hero">
      <div class="hero-badge"><i class="fas fa-sparkles"></i> SOFTWARE QUALITY INTELLIGENCE</div>
      <h1>Engineering Health Simplified with AI</h1>
      <p>Upload your codebase for automated architectural audit and defect detection powered by Gemini.</p>
      <div class="hero-actions">
        <button class="btn btn-primary" @click="showModal = true">
          <i class="fas fa-play-circle"></i> Start New Analysis
        </button>
        <router-link to="/audit-report" class="btn btn-secondary">
          <i class="fas fa-history"></i> Browse History
        </router-link>
      </div>
    </section>

    <!-- Summary Cards -->
    <section class="summary-grid">
      <div class="summary-card">
        <div class="summary-label">Health Score</div>
        <div class="summary-value">{{ summary.health_score ?? '--' }}</div>
        <div class="summary-meta">Overall architectural health.</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Total Issues</div>
        <div class="summary-value">{{ summary.total ?? '--' }}</div>
        <div class="summary-meta">Defects across codebase.</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Critical &amp; High</div>
        <div class="summary-value">{{ criticalHigh }}</div>
        <div class="summary-meta">High-priority issues.</div>
      </div>
    </section>

    <!-- Recent Scans -->
    <section class="section">
      <div class="report-card">
        <div class="report-header">
          <div>
            <h2 class="section-title"><i class="fas fa-clock"></i> Recent Analysis Reports</h2>
            <p class="section-subtitle">Access your previous architectural audits.</p>
          </div>
          <button class="refresh-btn" @click="loadScans">
            <i class="fas fa-sync-alt"></i> Refresh
          </button>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr><th>Project Name</th><th>Status</th><th>Issues</th><th>Date</th><th>Action</th></tr>
            </thead>
            <tbody>
              <tr v-if="loadingScans">
                <td colspan="5" style="text-align:center;padding:24px;color:var(--text-2);">
                  <i class="fas fa-spinner" style="animation:spin .8s linear infinite;"></i> Loading scans...
                </td>
              </tr>
              <tr v-else-if="!scans.length">
                <td colspan="5" style="text-align:center;padding:32px;color:var(--text-2);">
                  No scans yet.
                  <a href="#" @click.prevent="showModal = true" style="color:var(--accent);text-decoration:none;">Start one now</a>
                </td>
              </tr>
              <tr v-for="scan in scans" :key="scan.id">
                <td><i class="fas fa-layer-group"></i> {{ scan.scan_name || 'Untitled' }}</td>
                <td><span class="badge badge-success">{{ scan.status || 'COMPLETED' }}</span></td>
                <td>{{ scan.total_issues || 0 }}</td>
                <td>{{ new Date(scan.created_at).toLocaleString() }}</td>
                <td>
                  <router-link to="/issues" style="color:var(--accent);text-decoration:none;font-weight:600;">View Issues</router-link>
                  &nbsp;|&nbsp;
                  <a href="#" @click.prevent="deleteScan(scan.id)" style="color:var(--danger);text-decoration:none;font-weight:600;">Delete</a>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- New Scan Modal -->
    <Teleport to="body">
      <div class="modal-overlay" v-if="showModal" @click.self="closeModal">
        <div class="modal">
          <div class="modal-header">
            <h2>Start New Scan</h2>
            <button class="modal-close" @click="closeModal">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Project Folder Path</label>
              <input
                type="text"
                v-model="folderPath"
                placeholder="C:\Users\You\Desktop\my-project"
                @keypress.enter="startScan"
                ref="folderInput"
              />
              <div class="form-hint">Example: C:\path\to\project or /home/user/projects/project</div>
              <div class="form-error" v-if="errorMsg">{{ errorMsg }}</div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary btn-sm" @click="closeModal">Cancel</button>
            <button class="btn btn-primary btn-sm" :disabled="scanning" @click="startScan">
              <span v-if="!scanning">Start Scan</span>
              <span v-else class="spinner"></span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { API } from '../api.js'

const router = useRouter()

const summary = ref({})
const scans = ref([])
const loadingScans = ref(true)
const showModal = ref(false)
const folderPath = ref('')
const errorMsg = ref('')
const scanning = ref(false)
const folderInput = ref(null)

const criticalHigh = computed(() => {
  return ((summary.value.critical || 0) + (summary.value.high || 0)) || '--'
})

onMounted(() => {
  loadScans()
  loadDashboard()
})

async function loadDashboard() {
  try {
    const data = await API.dashboard()
    summary.value = data.summary || {}
  } catch (e) {
    console.warn('Dashboard data error:', e.message)
  }
}

async function loadScans() {
  loadingScans.value = true
  try {
    scans.value = await API.listScans() || []
  } catch (e) {
    console.error('Failed to load scans:', e)
    scans.value = []
  } finally {
    loadingScans.value = false
  }
}

async function deleteScan(id) {
  if (!confirm('Delete this scan?')) return
  try {
    await API.deleteScan(id)
    await loadScans()
  } catch (e) {
    alert('Error deleting scan: ' + e.message)
  }
}

async function startScan() {
  const path = folderPath.value.trim()
  if (!path) { errorMsg.value = 'Please enter a folder path'; return }
  scanning.value = true
  errorMsg.value = ''
  try {
    const result = await API.startScan(path, 'Project Scan')
    if (result && result.scan_id) {
      closeModal()
      await loadScans()
      setTimeout(() => router.push('/issues'), 500)
    } else {
      errorMsg.value = 'Failed to start scan'
    }
  } catch (e) {
    errorMsg.value = e.message || 'Error starting scan'
  } finally {
    scanning.value = false
  }
}

async function closeModal() {
  showModal.value = false
  folderPath.value = ''
  errorMsg.value = ''
}

// Focus input when modal opens
import { watch } from 'vue'
watch(showModal, async (val) => {
  if (val) {
    await nextTick()
    folderInput.value?.focus()
  }
})
</script>

<style scoped>
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 48px; }
.summary-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 24px; transition: all .3s ease; }
.summary-card:hover { border-color: var(--accent); box-shadow: 0 12px 28px rgba(124,58,237,.1); transform: translateY(-4px); }
.summary-label { font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--text-2); margin-bottom: 12px; }
.summary-value { font-size: 44px; font-weight: 800; color: var(--text); margin-bottom: 10px; }
.summary-meta { font-size: 13px; color: var(--text-2); line-height: 1.5; }
.section { margin-bottom: 48px; }
.section-title { font-size: 24px; font-weight: 700; margin-bottom: 0; display: flex; align-items: center; gap: 12px; }
.report-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 28px; }
.report-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.section-subtitle { color: var(--text-2); font-size: 14px; margin-top: 8px; line-height: 1.6; }
.refresh-btn { display: inline-flex; align-items: center; gap: 8px; padding: 12px 18px; border-radius: var(--radius-md); border: 1px solid var(--border); background: var(--bg); color: var(--text); font-weight: 600; cursor: pointer; transition: all .2s ease; font-family: var(--f-body); font-size: 14px; }
.refresh-btn:hover { border-color: var(--accent); color: var(--accent); }
</style>
