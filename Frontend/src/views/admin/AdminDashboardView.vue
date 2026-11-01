<template>
  <div class="admin-dashboard">
    <div class="admin-page">
      <header class="page-header">
        <h1>Admin Dashboard</h1>
      </header>

      <!-- VIEW TOGGLE -->
      <div class="toggle-container">
        <button
          :class="['toggle-btn', { active: activeTab === 'diagnostics' }]"
          @click="switchTab('diagnostics')"
        >
          Diagnostics
        </button>
        <button
          :class="['toggle-btn', { active: activeTab === 'hashes' }]"
          @click="switchTab('hashes')"
        >
          Schools Management
        </button>
        <button
          :class="['toggle-btn', { active: activeTab === 'awards' }]"
          @click="switchTab('awards')"
        >
          Awards Overview
        </button>
        <button
          :class="['toggle-btn', { active: activeTab === 'content' }]"
          @click="switchTab('content')"
        >
          Delegate Content
        </button>
        <button
          :class="['toggle-btn', { active: activeTab === 'committees' }]"
          @click="switchTab('committees')"
        >
          Committees
        </button>
        <button
          :class="['toggle-btn', { active: activeTab === 'timeline' }]"
          @click="switchTab('timeline')"
        >
          Timeline
        </button>
      </div>

      <KeepAlive>
        <component :is="activeComponent" />
      </KeepAlive>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import AwardsTab from './tabs/AwardsTab.vue'
import CommitteesTab from './tabs/CommitteesTab.vue'
import ContentTab from './tabs/ContentTab.vue'
import DiagnosticsTab from './tabs/DiagnosticsTab.vue'
import SchoolsTab from './tabs/SchoolsTab.vue'
import TimelineTab from './tabs/TimelineTab.vue'
import './admin-dashboard.css'

// One component per tab. Kept alive rather than re-created so that switching tabs does not
// throw away a half-filled form - which is how the single-component version behaved, and why
// the tabs' own entry hooks (`onActivated`) refresh data instead of relying on a remount.
const tabs = {
  diagnostics: DiagnosticsTab,
  hashes: SchoolsTab,
  committees: CommitteesTab,
  awards: AwardsTab,
  content: ContentTab,
  timeline: TimelineTab
}

// Tab ids keep their historical names ('hashes' is Schools Management) so the ids in the
// markup and any saved links do not change.
const activeTab = ref('diagnostics')
const activeComponent = computed(() => tabs[activeTab.value])

const switchTab = (tab) => {
  activeTab.value = tab
}
</script>
