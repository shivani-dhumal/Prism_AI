<template>
  <div class="app-container" style="width: 1200px; padding: 10px; margin: 0; background: white; color: #ccc;">
    
    <!-- Missing alt tag -->
    <img src="/logo.png">
    <img src="/banner.jpg" width="800">
    
    <!-- Non-semantic tags -->
    <div class="header">
      <h1>My App</h1>
      <div class="navigation">
        <a href="/"><img src="/home-icon.svg"></a>
        <a href="/about"></a>
        <a href="/contact"></a>
      </div>
    </div>

    <div class="main-content">
      <!-- Skipped heading hierarchy: h1 -> h3 -->
      <h3>Dashboard Section</h3>
      
      <!-- Icon-only button without aria -->
      <button @click="doSomething"><i class="icon-search"></i></button>
      <button @click="save" style="width: 20px; height: 20px;"><i class="fa fa-save"></i></button>
      
      <!-- Input without label -->
      <input type="text" placeholder="Search...">
      <input type="email">

      <!-- Inline style overuse -->
      <div style="color: red; font-size: 14px; margin: 10px; padding: 5px; background: blue; border: 1px solid green; border-radius: 4px;">
        Overly styled div
      </div>
      <div style="display: flex; justify-content: center; align-items: center; gap: 10px;">
        Another styled div
      </div>
      <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0;">
        Overlay
      </div>
      <div style="margin-top: 20px; padding: 15px; border-bottom: 2px solid #333;">
        Yet another inline
      </div>
    </div>

    <div class="sidebar">
      <h1>Second H1</h1>
      <p style="font-family: 'Comic Sans MS'; color: yellow; background: white;">Low contrast text</p>
    </div>

    <div class="footer">
      &copy; 2024 My App
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      message: 'Hello'
    }
  },
  methods: {
    doSomething() {
      console.log('clicked');
    },
    save() {
      console.log('saved');
    }
  }
}
</script>

<style>
.app-container {
  font-family: 'Arial';
}

.header {
  font-family: 'Helvetica';
}

.sidebar {
  font-family: 'Georgia';
}

.footer {
  font-family: 'Verdana';
}

.navigation a {
  width: 16px;
  height: 16px;
}

button {
  width: 24px;
  height: 24px;
}

.low-contrast {
  color: #ccc;
  background-color: #ddd;
}
</style>
