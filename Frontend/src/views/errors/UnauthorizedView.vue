<template>
  <div class="unauthorized-container">
    <div class="error-card">
      <div class="error-code">403</div>
      <h1>Access Denied</h1>
      <p>
        You do not have the required permissions to access this page. If you believe this is an error, please contact your committee administrator.
      </p>
      <button class="btn-home" @click="goHome">
        Return to Home Dashboard
      </button>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

const goHome = () => {
  router.push('/')
}
</script>

<style scoped>
.unauthorized-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 70vh;
  color: #00007e93;
  font-family: var(--font-theme);
}

.error-card {
  background-color: #ffffff;
  border: 1px solid #e8c604;
  border-radius: 8px;
  padding: 40px;
  text-align: center;
  max-width: 460px;
  width: 100%;
}

.error-code {
  font-size: 4.5rem;
  font-weight: bold;
  color: #ef4444;
  line-height: 1;
  margin-bottom: 12px;
}

.error-card h1 {
  margin: 0 0 12px 0;
  font-size: 1.4rem;
  color: #00007e;
}

.error-card p {
  color: #5b6b7d;
  font-size: 0.9rem;
  line-height: 1.5;
  margin-bottom: 24px;
}

.btn-home {
  background-color: #009ddbda;
  color: #00007e;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  font-weight: bold;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.btn-home:hover {
  background-color: #00007e;
  color: #ffffff;
}
</style>