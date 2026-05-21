<template>
  <div id="prism-app">
    <header class="header">
      <div class="header-left">
        <div class="logo">
          <i class="fas fa-shield-alt"></i> PrismAI
        </div>
        <nav class="nav">
          <router-link to="/" exact-active-class="active">Dashboard</router-link>
          <router-link to="/issues" active-class="active">Issues</router-link>
          <router-link to="/audit-report" active-class="active">Audit</router-link>
          <router-link to="/dependency-graph" active-class="active">Dependencies</router-link>
          <router-link to="/chatbot" active-class="active">Chatbot</router-link>
        </nav>
      </div>
      <div class="header-right">
        <button class="theme-toggle" @click="toggleTheme" :title="isDark ? 'Switch to light mode' : 'Switch to dark mode'">
          <i :class="isDark ? 'fas fa-sun' : 'fas fa-moon'"></i>
        </button>
      </div>
    </header>

    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const isDark = ref(false)

onMounted(() => {
  const saved = localStorage.getItem('theme') || 'light'
  if (saved === 'dark') {
    document.documentElement.classList.add('dark')
    isDark.value = true
  }
})

function toggleTheme() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}
</script>

<style>
/* FontAwesome CDN */
@import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css');

.header {
  background: var(--bg-alt);
  border-bottom: 1px solid var(--border);
  padding: 16px 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: var(--shadow-sm);
}
.header-left { display: flex; align-items: center; gap: 24px; }
.header-right { display: flex; align-items: center; gap: 12px; }

.logo {
  font-size: 20px; font-weight: 700;
  background: var(--accent-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  display: flex; align-items: center; gap: 8px;
}
.nav { display: flex; gap: 24px; }
.nav a {
  color: var(--text-2); text-decoration: none;
  font-size: 14px; font-weight: 500;
  transition: color .2s ease; padding: 4px 0;
  border-bottom: 2px solid transparent;
}
.nav a:hover, .nav a.active { color: var(--accent); border-bottom-color: var(--accent); }

.theme-toggle {
  background: var(--bg); border: 1px solid var(--border);
  border-radius: var(--radius-md); width: 36px; height: 36px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  color: var(--text-2); transition: all .2s ease; font-size: 14px;
}
.theme-toggle:hover { color: var(--accent); border-color: var(--accent); background: var(--bg-card); }

@media (max-width: 640px) {
  .header { padding: 12px 16px; }
  .nav { gap: 12px; }
  .nav a { font-size: 13px; }
}
</style>
