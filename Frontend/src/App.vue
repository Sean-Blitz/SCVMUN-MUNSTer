<template>
  <!-- Global Toast Notification Container -->
  <div class="toast-container">
    <div
      v-for="toast in toastStore.toasts"
      :key="toast.id"
      :class="['toast-banner', toast.type]"
    >
      <span>{{ toast.message }}</span>
      <button @click="toastStore.removeToast(toast.id)">✕</button>
    </div>
  </div>

  <router-view />
</template>

<script setup>
import { useToastStore } from './stores/toast'
const toastStore = useToastStore()
</script>

<style>
body {
  margin: 0;
  background-color: #1a1d21;
}

.toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.toast-banner {
  min-width: 280px;
  padding: 12px 16px;
  border-radius: 6px;
  color: #fff;
  font-family: sans-serif;
  font-size: 0.9rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.toast-banner.error {
  background-color: #ef4444;
}

.toast-banner.success {
  background-color: #10b981;
}

.toast-banner button {
  background: transparent;
  border: none;
  color: #fff;
  cursor: pointer;
  font-weight: bold;
  margin-left: 12px;
}
</style>