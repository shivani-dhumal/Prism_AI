<template>
  <div>
    <section class="hero" style="margin-bottom:32px;text-align:left;">
      <h1>Dependency Graph</h1>
      <p>Interactive visualization of your project's file dependencies.</p>
    </section>

    <div class="graph-toolbar">
      <div class="toolbar-left">
        <span class="project-badge" v-if="projectName">
          <i class="fas fa-folder"></i> {{ projectName }}
        </span>
        <span class="stat-chip"><i class="fas fa-circle-nodes"></i> {{ nodeCount }} files</span>
        <span class="stat-chip"><i class="fas fa-arrow-right-arrow-left"></i> {{ edgeCount }} dependencies</span>
      </div>
      <div class="toolbar-right">
        <input
          v-model="searchTerm"
          placeholder="Search file..."
          class="graph-search"
          @input="onSearch"
        />
        <button class="btn btn-secondary btn-sm" @click="loadGraph">
          <i class="fas fa-sync-alt"></i> Refresh
        </button>
      </div>
    </div>

    <div class="graph-card">
      <div v-if="loading" class="graph-loading">
        <div class="spinner" style="width:32px;height:32px;border-width:3px;"></div>
        <p>Building dependency graph...</p>
      </div>
      <div v-else-if="error" class="graph-loading" style="color:var(--danger);">
        <i class="fas fa-exclamation-triangle" style="font-size:32px;"></i>
        <p>{{ error }}</p>
        <button class="btn btn-secondary btn-sm" style="margin-top:16px;" @click="loadGraph">Retry</button>
      </div>
      <div v-else ref="cyContainer" class="cy-container"></div>
    </div>

    <!-- Selected node info panel -->
    <div class="node-panel" v-if="selectedNode">
      <div class="node-panel-header">
        <div class="node-panel-title">
          <i class="fas fa-file-code"></i>
          {{ selectedNode.label }}
        </div>
        <button class="node-panel-close" @click="selectedNode = null">&times;</button>
      </div>
      <div class="node-panel-body">
        <div class="node-meta-row"><span class="meta-key">Path</span><span class="meta-val mono">{{ selectedNode.id }}</span></div>
        <div class="node-meta-row"><span class="meta-key">Bugs</span>
          <span class="meta-val">
            <span v-if="selectedNode.bug_count" :class="`badge badge-${(selectedNode.top_severity||'').toLowerCase()||'info'}`">
              {{ selectedNode.bug_count }} issue{{ selectedNode.bug_count > 1 ? 's' : '' }}
            </span>
            <span v-else class="meta-val" style="color:var(--success);">Clean</span>
          </span>
        </div>
        <div class="node-meta-row"><span class="meta-key">Imports</span><span class="meta-val">{{ selectedNode.outEdges }} file{{ selectedNode.outEdges > 1 ? 's' : '' }}</span></div>
        <div class="node-meta-row"><span class="meta-key">Imported by</span><span class="meta-val">{{ selectedNode.inEdges }} file{{ selectedNode.inEdges > 1 ? 's' : '' }}</span></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { API } from '../api.js'

const loading = ref(true)
const error = ref('')
const projectName = ref('')
const nodeCount = ref(0)
const edgeCount = ref(0)
const cyContainer = ref(null)
const selectedNode = ref(null)
const searchTerm = ref('')

let cy = null

onMounted(async () => {
  await loadCytoscape()
  await loadGraph()
})

onUnmounted(() => {
  if (cy) cy.destroy()
})

async function loadCytoscape() {
  if (window.cytoscape) return
  await new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js'
    s.onload = resolve
    s.onerror = reject
    document.head.appendChild(s)
  })
}

async function loadGraph() {
  loading.value = true
  error.value = ''
  try {
    const data = await API.dependencies()
    projectName.value = data.project_name || ''
    nodeCount.value = data.nodes?.length || 0
    edgeCount.value = data.edges?.length || 0
    buildGraph(data.nodes || [], data.edges || [])
  } catch (e) {
    error.value = 'Failed to load dependency graph: ' + (e.message || e)
  } finally {
    loading.value = false
  }
}

function buildGraph(nodes, edges) {
  if (!window.cytoscape || !cyContainer.value) return
  if (cy) cy.destroy()

  const elements = [
    ...nodes.map(n => ({ data: n.data || { id: n.id || n.data?.id, label: n.label || n.data?.label, bug_count: n.bug_count, top_severity: n.top_severity } })),
    ...edges.map(e => ({ data: e.data || { source: e.source || e.data?.source, target: e.target || e.data?.target, id: `${e.source||e.data?.source}-${e.target||e.data?.target}` } })),
  ]

  cy = window.cytoscape({
    container: cyContainer.value,
    elements,
    style: [
      {
        selector: 'node',
        style: {
          label: 'data(label)',
          'font-size': 11,
          'font-family': "'Geist', sans-serif",
          'text-valign': 'bottom',
          'text-halign': 'center',
          'text-margin-y': 6,
          color: getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#1f2937',
          'background-color': '#7c3aed',
          'border-width': 2,
          'border-color': '#a78bfa',
          width: 32,
          height: 32,
        },
      },
      {
        selector: 'node[bug_count > 0]',
        style: {
          'background-color': '#dc2626',
          'border-color': '#ef4444',
        },
      },
      {
        selector: 'node:selected',
        style: {
          'background-color': '#f59e0b',
          'border-color': '#fbbf24',
          'border-width': 3,
        },
      },
      {
        selector: 'node.highlighted',
        style: {
          'background-color': '#10b981',
          'border-color': '#34d399',
        },
      },
      {
        selector: 'edge',
        style: {
          width: 1.5,
          'line-color': '#6366f1',
          'target-arrow-color': '#6366f1',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          opacity: 0.6,
        },
      },
      {
        selector: 'edge:selected',
        style: { 'line-color': '#f59e0b', 'target-arrow-color': '#f59e0b', opacity: 1 },
      },
    ],
    layout: {
      name: 'cose',
      animate: true,
      animationDuration: 600,
      nodeRepulsion: 4500,
      idealEdgeLength: 80,
      gravity: 0.6,
      numIter: 1000,
    },
  })

  cy.on('tap', 'node', (evt) => {
    const node = evt.target
    const id = node.data('id')
    const outEdges = cy.edges(`[source="${id}"]`).length
    const inEdges = cy.edges(`[target="${id}"]`).length
    selectedNode.value = {
      id,
      label: node.data('label'),
      bug_count: node.data('bug_count') || 0,
      top_severity: node.data('top_severity') || '',
      outEdges,
      inEdges,
    }
  })

  cy.on('tap', (evt) => {
    if (evt.target === cy) selectedNode.value = null
  })
}

function onSearch() {
  if (!cy) return
  const q = searchTerm.value.toLowerCase()
  cy.nodes().removeClass('highlighted')
  if (!q) return
  cy.nodes().filter(n => n.data('label').toLowerCase().includes(q)).addClass('highlighted')
}
</script>

<style scoped>
.graph-toolbar { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:20px; flex-wrap:wrap; }
.toolbar-left { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
.toolbar-right { display:flex; align-items:center; gap:10px; }
.project-badge { background:rgba(124,58,237,.1); color:var(--accent); border:1px solid rgba(124,58,237,.3); border-radius:20px; padding:5px 12px; font-size:12px; font-weight:600; display:flex; align-items:center; gap:6px; }
.stat-chip { background:var(--bg-alt); border:1px solid var(--border); border-radius:20px; padding:5px 12px; font-size:12px; color:var(--text-2); font-weight:500; display:flex; align-items:center; gap:6px; }
.graph-search { padding:8px 12px; border:1px solid var(--border); border-radius:var(--radius-md); background:var(--bg); color:var(--text); font-family:var(--f-body); font-size:13px; width:200px; }
.graph-search:focus { outline:none; border-color:var(--accent); }
.graph-card { background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-lg); overflow:hidden; box-shadow:var(--shadow-sm); }
.graph-loading { height:560px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:16px; color:var(--text-2); }
.cy-container { height:560px; width:100%; }
/* Node panel */
.node-panel { margin-top:20px; background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-lg); overflow:hidden; box-shadow:var(--shadow-sm); animation:slideUp .2s ease; }
.node-panel-header { padding:14px 20px; background:var(--bg-alt); border-bottom:1px solid var(--border); display:flex; justify-content:space-between; align-items:center; }
.node-panel-title { font-weight:700; font-size:15px; display:flex; align-items:center; gap:8px; color:var(--accent); }
.node-panel-close { background:none; border:none; font-size:20px; cursor:pointer; color:var(--text-2); }
.node-panel-body { padding:16px 20px; display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.node-meta-row { display:flex; flex-direction:column; gap:4px; }
.meta-key { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:var(--text-3); }
.meta-val { font-size:13px; color:var(--text); }
.mono { font-family:var(--f-mono); font-size:11px; word-break:break-all; }
@media (max-width:640px) { .node-panel-body { grid-template-columns:1fr; } }
</style>
