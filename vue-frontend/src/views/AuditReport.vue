<template>
  <div>
    <section class="hero" style="margin-bottom:32px;">
      <h1>Audit Report</h1>
      <p>Comprehensive analysis of your codebase health and security.</p>
    </section>

    <!-- Stats -->
    <div class="stats-grid">
      <div class="stat-box">
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-label">Total Issues</div>
      </div>
      <div class="stat-box">
        <div class="stat-value">{{ stats.critical }}</div>
        <div class="stat-label">Critical</div>
      </div>
      <div class="stat-box">
        <div class="stat-value">{{ stats.high }}</div>
        <div class="stat-label">High</div>
      </div>
      <div class="stat-box">
        <div class="stat-value">{{ stats.medium }}</div>
        <div class="stat-label">Medium</div>
      </div>
    </div>

    <!-- Filters -->
    <div class="audit-filters">
      <input type="text" v-model="searchQuery" placeholder="Search issues..." style="flex:1;" />
      <select v-model="severityFilter">
        <option value="">All Severities</option>
        <option value="CRITICAL">Critical</option>
        <option value="HIGH">High</option>
        <option value="MEDIUM">Medium</option>
        <option value="LOW">Low</option>
      </select>
    </div>

    <!-- Table -->
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>File</th><th>Severity</th><th>Issue</th><th>Line</th><th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="5" style="text-align:center;padding:24px;color:var(--text-2);">
              <i class="fas fa-spinner" style="animation:spin .8s linear infinite;"></i> Loading...
            </td>
          </tr>
          <tr v-else-if="!filteredIssues.length">
            <td colspan="5" style="text-align:center;padding:24px;color:var(--text-2);">No issues found</td>
          </tr>
          <tr v-for="issue in filteredIssues" :key="issue.id">
            <td><small>{{ issue.file_name || issue.file_path }}</small></td>
            <td><span :class="`badge badge-${(issue.severity||'medium').toLowerCase()}`">{{ issue.severity }}</span></td>
            <td>{{ issue.title || 'Issue' }}</td>
            <td>Line {{ issue.line_number }}</td>
            <td><span class="badge badge-info">{{ issue.status || 'OPEN' }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { API } from '../api.js'

const allIssues = ref([])
const loading = ref(true)
const searchQuery = ref('')
const severityFilter = ref('')

const stats = computed(() => ({
  total: allIssues.value.length,
  critical: allIssues.value.filter(i => i.severity === 'CRITICAL').length,
  high: allIssues.value.filter(i => i.severity === 'HIGH').length,
  medium: allIssues.value.filter(i => i.severity === 'MEDIUM').length,
}))

const filteredIssues = computed(() => {
  let list = allIssues.value
  const q = searchQuery.value.toLowerCase()
  if (q) list = list.filter(i => (i.title || '').toLowerCase().includes(q) || (i.file_name || '').toLowerCase().includes(q))
  if (severityFilter.value) list = list.filter(i => i.severity === severityFilter.value)
  return list
})

onMounted(async () => {
  try {
    allIssues.value = await API.allBugs() || []
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.stats-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:16px; margin-bottom:32px; }
.stat-box { background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-lg); padding:16px; text-align:center; }
.stat-value { font-size:32px; font-weight:700; color:var(--accent); }
.stat-label { font-size:12px; color:var(--text-2); margin-top:4px; }
.audit-filters { display:flex; gap:12px; margin-bottom:24px; flex-wrap:wrap; }
.audit-filters input, .audit-filters select { padding:10px 12px; border:1px solid var(--border); border-radius:var(--radius-md); background:var(--bg); color:var(--text); font-family:var(--f-body); font-size:13px; }
.audit-filters input:focus, .audit-filters select:focus { outline:none; border-color:var(--accent); }
</style>
