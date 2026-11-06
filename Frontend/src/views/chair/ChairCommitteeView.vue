<template>
  <div class="chair-page">
    <!-- TOP VIEW TOGGLE BUTTONS -->
    <div class="toggle-container">
      <button 
        class="toggle-btn active" 
        @click="switchView('/chair/committee')"
      >
        Committee Overview
      </button>
      <button 
        class="toggle-btn" 
        @click="switchView('/chair/grading')"
      >
        Position Paper Grading
      </button>
      <button 
        class="toggle-btn" 
        @click="switchView('/chair/awards')"
      >
        Awards
      </button>
    </div>

    <!-- MAIN TWO-COLUMN GRID -->
    <div class="overview-grid">
      <!-- LEFT COLUMN (WELCOME & METRICS) -->
      <div class="left-column">
        <!-- WELCOME PANEL -->
        <section class="panel welcome-panel">
          <h2 class="welcome-heading">Welcome, {{ chairName }}!</h2>
          <p class="welcome-subtext">
            Manage your committee sessions, monitor delegate position paper grading, and track conference milestones below.
          </p>
        </section>

        <!-- COMMITTEE METRICS PANEL -->
        <section class="panel">
          <h2 class="panel-title">Committee Information</h2>
          
          <div class="metrics-list">
            <div class="metric-card">
              <span class="metric-label">Committee Name</span>
              <span class="metric-value committee-name">{{ committeeName || 'Unassigned' }}</span>
            </div>

            <div class="metric-card">
              <span class="metric-label">Delegates Registered</span>
              <span class="metric-value fraction">
                <strong>{{ delegatesRegistered }}</strong> / {{ totalDelegates }}
              </span>
            </div>

            <div class="metric-card">
              <span class="metric-label">Position Papers Graded</span>
              <span class="metric-value fraction">
                <strong class="graded-count">{{ papersGraded }}</strong> / {{ totalPapersSubmitted }}
              </span>
            </div>
          </div>
        </section>
      </div>

      <!-- RIGHT COLUMN (TIMELINE & PHASES) -->
      <div class="right-column">
        <section class="panel full-height-panel">
          <h2 class="panel-title">Conference Timeline & Active Phase</h2>

          <!-- PRE-CONFERENCE TIMELINE -->
          <div class="timeline-section">
            <h3 class="section-sub-title">Pre-Conference</h3>
            <div class="timeline-list">
              <div 
                v-for="(event, index) in timeline.preConference" 
                :key="'pre-' + index"
                :class="['timeline-item', getEventStatus(event.timestamp, getNextTimestamp('pre', index))]"
              >
                <div class="node-indicator">
                  <span v-if="getEventStatus(event.timestamp, getNextTimestamp('pre', index)) === 'completed'">✓</span>
                  <span v-else-if="getEventStatus(event.timestamp, getNextTimestamp('pre', index)) === 'active'">▶</span>
                  <span v-else class="dot">•</span>
                </div>
                <div class="timeline-content">
                  <div class="event-header">
                    <span class="event-label">{{ event.label }}</span>
                    <span class="status-pill">{{ getStatusLabel(getEventStatus(event.timestamp, getNextTimestamp('pre', index))) }}</span>
                  </div>
                  <span class="event-time">{{ formatDate(event.timestamp) }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- DURING CONFERENCE TIMELINE -->
          <div class="timeline-section">
            <h3 class="section-sub-title">During Conference</h3>
            <div class="timeline-list">
              <div 
                v-for="(event, index) in timeline.duringConference" 
                :key="'during-' + index"
                :class="['timeline-item', getEventStatus(event.timestamp, getNextTimestamp('during', index))]"
              >
                <div class="node-indicator">
                  <span v-if="getEventStatus(event.timestamp, getNextTimestamp('during', index)) === 'completed'">✓</span>
                  <span v-else-if="getEventStatus(event.timestamp, getNextTimestamp('during', index)) === 'active'">▶</span>
                  <span v-else class="dot">•</span>
                </div>
                <div class="timeline-content">
                  <div class="event-header">
                    <span class="event-label">{{ event.label }}</span>
                    <span class="status-pill">{{ getStatusLabel(getEventStatus(event.timestamp, getNextTimestamp('during', index))) }}</span>
                  </div>
                  <span class="event-time">{{ formatDate(event.timestamp) }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'

const router = useRouter()
const toastStore = useToastStore()

// Reactive State
const chairName = ref('')
const committeeName = ref('')
const delegatesRegistered = ref(0)
const totalDelegates = ref(0)
const papersGraded = ref(0)
const totalPapersSubmitted = ref(0)

const timeline = ref({
  preConference: [],
  duringConference: []
})

// Navigation Handler
const switchView = (path) => {
  router.push(path)
}

// Format ISO Timestamps for Display
const formatDate = (isoString) => {
  if (!isoString) return ''
  const date = new Date(isoString)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  })
}

// Get next timestamp in line to determine current active window
const getNextTimestamp = (section, index) => {
  const list = section === 'pre' ? timeline.value.preConference : timeline.value.duringConference
  if (index + 1 < list.length) {
    return list[index + 1].timestamp
  }
  
  // If at end of pre-conference, bridge to first item of during-conference
  if (section === 'pre' && timeline.value.duringConference?.length > 0) {
    return timeline.value.duringConference[0].timestamp
  }
  
  return null
}

// Compare current browser time against event windows
const getEventStatus = (eventTimestamp, nextTimestamp) => {
  const now = new Date()
  const eventTime = new Date(eventTimestamp)
  const nextTime = nextTimestamp ? new Date(nextTimestamp) : null

  if (now < eventTime) {
    return 'upcoming'
  } else if (nextTime && now >= nextTime) {
    return 'completed'
  } else if (now >= eventTime && (!nextTime || now < nextTime)) {
    return 'active'
  } else {
    return 'completed'
  }
}

const getStatusLabel = (status) => {
  switch (status) {
    case 'completed': return 'Completed'
    case 'active': return 'In Progress'
    case 'upcoming': default: return 'Upcoming'
  }
}

// Fetch initial data from backend on mount
onMounted(async () => {
  try {
    const response = await apiClient.get('/chair/committee/overview')
    
    // Assign stats and committee details
    chairName.value = response.data.chairName
    committeeName.value = response.data.committeeName
    delegatesRegistered.value = response.data.delegatesRegistered
    totalDelegates.value = response.data.totalDelegates
    papersGraded.value = response.data.papersGraded
    totalPapersSubmitted.value = response.data.totalPapersSubmitted

    // Assign schedule timeline
    timeline.value = response.data.timeline
  } catch (error) {
    // Errors automatically trigger global Toast notifications via client.js
  }
})
</script>

<style scoped>
/* ============================================================ PAGE ====== */
/* White surface, navy ink and hairline rules, the same as the delegate dashboard and the
   advisor views. Colour is spent on state only: gold for something due, accent for the live
   window, green for a finished count. */
.chair-page {
  --ink: #03045e;
  --ink-2: #232d5c;
  --muted: #63708c;
  --line: rgba(3, 4, 94, 0.09);
  --accent: #009ddb;
  --green: #15803d;
  --gold: #7a5c00;
  --red: #b42318;
  --gap: clamp(12px, 1.6vh, 18px);
  --radius: 16px;
  --ease: cubic-bezier(0.22, 1, 0.36, 1);
  --font:
    'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto,
    'Helvetica Neue', Arial, sans-serif;

  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: clamp(14px, 2.1vh, 24px) clamp(16px, 2.4vw, 34px);
  color: var(--muted);
  font-family: var(--font);
  font-size: clamp(0.85rem, 1.6vh, 1rem);
  line-height: 1.5;
  letter-spacing: 0.005em;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background: #ffffff;
}

/* =========================================================== TOGGLE ===== */
/* Segmented pills: the page in view carries the navy weight, the others stay quiet
   outlines. */
.toggle-container {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.toggle-btn {
  min-width: 210px;
  padding: 10px 22px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background-color: #ffffff;
  color: var(--muted);
  font-family: inherit;
  font-size: 0.76em;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  cursor: pointer;
  transition:
    background-color 0.25s ease,
    border-color 0.25s ease,
    color 0.25s ease,
    transform 0.25s var(--ease);
}

.toggle-btn:hover:not(.active) {
  border-color: rgba(3, 4, 94, 0.18);
  color: var(--ink);
  transform: translateY(-1px);
}

.toggle-btn.active {
  border-color: var(--ink);
  background-color: var(--ink);
  color: #ffffff;
}

/* ============================================================ GRID ====== */
.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--gap);
  align-items: start;
}

.left-column,
.right-column {
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  min-width: 0;
}

/* =========================================================== PANELS ===== */
/* White cards on white: a hairline and one soft shadow carry the separation. */
.panel {
  display: flex;
  flex-direction: column;
  gap: clamp(9px, 1.3vh, 14px);
  min-width: 0;
  padding: clamp(14px, 1.9vh, 20px) clamp(14px, 1.5vw, 22px);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.99), rgba(255, 255, 255, 0.92));
  box-shadow:
    0 1px 2px rgba(3, 4, 94, 0.04),
    0 24px 48px -38px rgba(3, 4, 94, 0.45);
  transition:
    border-color 0.35s ease,
    box-shadow 0.35s ease;
  animation: panel-in 0.8s var(--ease) both;
}

.panel:hover {
  border-color: rgba(3, 4, 94, 0.16);
  box-shadow:
    0 1px 2px rgba(3, 4, 94, 0.05),
    0 22px 44px -38px rgba(3, 4, 94, 0.35);
}

@keyframes panel-in {
  from {
    opacity: 0;
    transform: translate3d(0, 14px, 0);
  }
}

.left-column .panel:nth-child(2) {
  animation-delay: 0.08s;
}

.right-column .panel {
  animation-delay: 0.16s;
}

.full-height-panel {
  height: 100%;
}

/* The welcome card keeps a single accent edge: the only colour the panel carries. */
.welcome-panel {
  border-left: 3px solid var(--accent);
}

.welcome-heading {
  margin: 0;
  font-size: 1.25em;
  font-weight: 650;
  line-height: 1.25;
  letter-spacing: -0.01em;
  color: var(--ink);
}

.welcome-subtext {
  margin: 0;
  font-size: 0.86em;
  line-height: 1.55;
  color: var(--muted);
}

.panel-title {
  margin: 0;
  padding-bottom: 9px;
  border-bottom: 1px solid var(--line);
  font-size: 1.04em;
  font-weight: 650;
  line-height: 1.25;
  letter-spacing: -0.005em;
  color: var(--ink);
}

.section-sub-title {
  margin: 0;
  font-size: 0.64em;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
}

/* ========================================================== METRICS ===== */
.metrics-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 11px;
  background-color: #f7fafd;
}

.metric-label {
  font-size: 0.66em;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.metric-value {
  font-size: 0.92em;
  font-weight: 600;
  color: var(--ink);
}

.committee-name {
  color: var(--ink);
}

.fraction {
  font-size: 0.86em;
  color: var(--muted);
}

.fraction strong {
  font-size: 1.15em;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}

.graded-count {
  color: var(--green) !important;
}

/* ========================================================== TIMELINE ==== */
.timeline-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.timeline-section + .timeline-section {
  margin-top: 6px;
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 13px;
  border: 1px solid transparent;
  border-radius: 12px;
  background-color: #f7fafd;
  transition:
    border-color 0.3s ease,
    background-color 0.3s ease,
    transform 0.3s var(--ease);
}

.timeline-item:hover {
  border-color: var(--line);
  transform: translateX(2px);
}

.node-indicator {
  flex: none;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  margin-top: 1px;
  border: 1px solid var(--line);
  border-radius: 50%;
  background-color: #ffffff;
  color: var(--muted);
  font-size: 0.72em;
  font-weight: 700;
}

.timeline-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.event-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.event-label {
  font-size: 0.88em;
  font-weight: 600;
  color: var(--ink-2);
}

.event-time {
  font-size: 0.76em;
  color: var(--muted);
}

.status-pill {
  flex: none;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 0.62em;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  white-space: nowrap;
}

/* Completed: settled back and quietly green. */
.timeline-item.completed {
  opacity: 0.75;
}

.timeline-item.completed .node-indicator {
  border-color: transparent;
  background-color: var(--green);
  color: #ffffff;
}

.timeline-item.completed .status-pill {
  background-color: rgba(22, 163, 74, 0.1);
  color: var(--green);
}

/* Active: the one row that is live right now. */
.timeline-item.active {
  border-color: rgba(0, 157, 219, 0.35);
  background-color: rgba(0, 157, 219, 0.05);
}

.timeline-item.active .node-indicator {
  border-color: transparent;
  background-color: var(--accent);
  color: #ffffff;
}

.timeline-item.active .event-label {
  color: var(--ink);
}

.timeline-item.active .status-pill {
  background-color: rgba(0, 157, 219, 0.14);
  color: #0079ab;
}

/* Upcoming: waiting, not wrong. */
.timeline-item.upcoming .status-pill {
  border: 1px solid var(--line);
  background-color: #ffffff;
  color: var(--muted);
}

/* ========================================================== RESPONSIVE === */
@media (max-width: 900px) {
  .overview-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .toggle-btn {
    flex: 1;
    min-width: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .panel {
    animation: none;
  }

  .timeline-item {
    transition: none;
  }
}
</style>
