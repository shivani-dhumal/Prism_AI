import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

import Dashboard from './views/Dashboard.vue'
import Issues from './views/Issues.vue'
import AuditReport from './views/AuditReport.vue'
import DependencyGraph from './views/DependencyGraph.vue'
import Chatbot from './views/Chatbot.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/issues', component: Issues },
  { path: '/audit-report', component: AuditReport },
  { path: '/dependency-graph', component: DependencyGraph },
  { path: '/chatbot', component: Chatbot },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

const app = createApp(App)
app.use(router)
app.mount('#app')
