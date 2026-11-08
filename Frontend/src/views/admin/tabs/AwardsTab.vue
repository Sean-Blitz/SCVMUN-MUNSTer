<template>
<div class="section-card">
  <div class="card-header-action">
    <h2>Conference Awards Overview</h2>
    <button class="btn-refresh" :disabled="loadingAwards" @click="loadAwards">
      <AppIcon name="refresh" />
      <span>{{ loadingAwards ? 'Loading...' : 'Reload' }}</span>
    </button>
  </div>
  <p class="section-desc">
    Read-only report of every committee's award assignments.
  </p>

  <div v-if="awardsCommittees.length" class="committee-awards-list">
    <div v-for="committee in awardsCommittees" :key="committee.committee" class="awards-card">
      <h3>{{ committee.committee }}</h3>
      <div v-for="entry in committee.awards" :key="entry.country" class="award-row">
        <span class="award-country">{{ entry.country }}</span>
        <span class="award-name">{{ entry.award }}</span>
      </div>
      <div v-if="!committee.awards.length" class="empty-state">No awards assigned.</div>
    </div>
  </div>
  <div v-else class="empty-state">No award data available.</div>
</div>
</template>

<script setup>
import AppIcon from '@/components/AppIcon.vue'
import { onActivated, ref } from 'vue'
import apiClient from '@/api/client'

// ---------- Awards state ----------
const awardsCommittees = ref([])
const loadingAwards = ref(false)

// ---------- Awards actions ----------
const loadAwards = async () => {
  loadingAwards.value = true
  try {
    const response = await apiClient.get('/admin/awards')
    awardsCommittees.value = response.data.committees
  } catch (error) {
    // Errors automatically pop up via global toast interceptor
  } finally {
    loadingAwards.value = false
  }
}

// Refetched on entry: the report is read-only, so there is never a draft to protect.
onActivated(loadAwards)

</script>
