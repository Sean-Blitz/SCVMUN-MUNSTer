<template>
  <div class="not-found-container">
    <div class="error-card">
      <div class="error-code">404</div>
      <h1>Page Not Found</h1>
      <p>
        The page you are looking for doesn't exist or has been moved.
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
.not-found-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 70vh;
  color: #ffffff;
  font-family: Arial, sans-serif;
}

.error-card {
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  border-radius: 8px;
  padding: 40px;
  text-align: center;
  max-width: 460px;
  width: 100%;
}

.error-code {
  font-size: 4.5rem;
  font-weight: bold;
  color: #6366f1;
  line-height: 1;
  margin-bottom: 12px;
}

.error-card h1 {
  margin: 0 0 12px 0;
  font-size: 1.4rem;
  color: #ffffff;
}

.error-card p {
  color: #aaaaaa;
  font-size: 0.9rem;
  line-height: 1.5;
  margin-bottom: 24px;
}

.btn-home {
  background-color: #6366f1;
  color: #ffffff;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  font-weight: bold;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.btn-home:hover {
  background-color: #4f46e5;
}
</style>