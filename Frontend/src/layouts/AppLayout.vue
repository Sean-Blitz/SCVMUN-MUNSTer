<template>
  <div class="app-layout">
    <!-- TOP GLOBAL NAVIGATION BAR -->
    <header class="global-navbar">
      <div class="navbar-left">
        <router-link to="/" class="logo-link">
          <!-- Fallback to placeholder if asset is missing -->
          <img 
            src="@/assets/logo.png" 
            alt="Conference Logo" 
            class="app-logo"
            @error="handleImageError"
          />
          <span class="brand-title">MUN Portal</span>
        </router-link>
      </div>

      <!-- CURRENT USER & SESSION INFO -->
      <div class="navbar-right">
        <div class="user-info">
          <span class="user-name">{{ currentUser.name }}</span>
          <span class="role-badge" :class="currentUser.role">{{ currentUser.role }}</span>
        </div>

        <button class="btn-logout" @click="handleLogout">
          Logout
        </button>
      </div>
    </header>

    <!-- MAIN ROUTER VIEWPORT -->
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import apiClient from '../api/client'

const router = useRouter()
const authStore = useAuthStore()

const currentUser = computed(() => authStore.user || { name: 'Guest', role: 'none' })

const handleLogout = async () => {
  try {
    // Revoke the session server-side too; a failure must not block signing out locally.
    await apiClient.post('/auth/logout')
  } catch (error) {
    // Ignored on purpose: the token is cleared below regardless.
  }
  authStore.logout()
  router.push('/')
}
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: #ffffff;
  color: #00007e93;
  font-family: Arial, sans-serif;
}

/* TOP NAVBAR */
.global-navbar {
  height: 60px;
  background-color: #ffffff;
  border-bottom: 1px solid #e8c604;
  padding: 0 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 100;
}

.navbar-left {
  display: flex;
  align-items: center;
}

.logo-link {
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
  color: #00007e93;
}

.app-logo {
  height: 36px;
  width: auto;
  object-fit: contain;
}

.brand-title {
  font-size: 1.1rem;
  font-weight: bold;
  letter-spacing: 0.5px;
}

/* USER INFO & LOGOUT */
.navbar-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-name {
  font-size: 0.9rem;
  color: #00007e93;
  font-weight: 500;
}

.role-badge {
  font-size: 0.75rem;
  text-transform: uppercase;
  font-weight: bold;
  padding: 2px 8px;
  border-radius: 4px;
}

.role-badge.chair {
  background-color: #009ddbda;
  color: #00007e;
  border: 1px solid #009ddb;
}

.role-badge.admin {
  background-color: #00007e;
  color: #ffffff;
  border: 1px solid #e8c604;
}

.role-badge.delegate {
  background-color: #dcfce7;
  color: #166534;
  border: 1px solid #16a34a;
}

.btn-logout {
  background-color: #f5fafd;
  color: #ef4444;
  border: 1px solid #ef4444;
  padding: 6px 14px;
  border-radius: 4px;
  font-size: 0.85rem;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-logout:hover {
  background-color: #dc2626;
  color: #ffffff;
}

/* MAIN VIEW CONTAINER */
.main-content {
  flex: 1;
  padding: 20px;
  box-sizing: border-box;
}
</style>