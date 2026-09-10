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

const router = useRouter()

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
  if (section === 'pre' && timeline.value.duringConference.length > 0) {
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

// Fetch initial data on mount
onMounted(async () => {
  // Mock API payload response
  chairName.value = 'Sarah'
  committeeName.value = 'Disarmament and International Security (DISEC)'
  delegatesRegistered.value = 18
  totalDelegates.value = 20
  papersGraded.value = 14
  totalPapersSubmitted.value = 18

  timeline.value = {
    preConference: [
      { label: 'Background Guide Published', timestamp: '2026-08-15T09:00:00Z' },
      { label: 'Position Paper Deadline', timestamp: '2026-09-01T23:59:00Z' },
      { label: 'Pre-Conference Chair Briefing', timestamp: '2026-09-06T18:00:00Z' }
    ],
    duringConference: [
      { label: 'Roll Call & Opening Statements (Session 1)', timestamp: '2026-09-07T08:30:00Z' },
      { label: 'Unmoderated Caucusing & Working Papers', timestamp: '2026-09-07T11:00:00Z' },
      { label: 'Draft Resolution Review (Session 2)', timestamp: '2026-09-07T14:00:00Z' },
      { label: 'Voting Procedure & Closing Session', timestamp: '2026-09-07T16:30:00Z' }
    ]
  }
})
</script>

<style scoped>
.chair-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  color: #ffffff;
  font-family: Arial, sans-serif;
}

/* TOP TOGGLE BUTTONS */
.toggle-container {
  display: flex;
  justify-content: center;
  gap: 15px;
}

.toggle-btn {
  width: 220px;
  height: 40px;
  background-color: #2a2e35;
  color: #aaaaaa;
  border: 1px solid #3f444e;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s ease;
}

.toggle-btn.active {
  background-color: #6366f1;
  color: #ffffff;
  border-color: #6366f1;
}

.toggle-btn:hover:not(.active) {
  background-color: #3f444e;
  color: #ffffff;
}

/* 50/50 TWO-COLUMN GRID */
.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.left-column, .right-column {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* PANELS */
.panel {
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
}

.full-height-panel {
  height: 100%;
}

.welcome-panel {
  border-left: 4px solid #6366f1;
}

.welcome-heading {
  margin: 0 0 8px 0;
  font-size: 1.4rem;
  color: #ffffff;
}

.welcome-subtext {
  margin: 0;
  color: #aaaaaa;
  font-size: 0.95rem;
  line-height: 1.5;
}

.panel-title {
  font-size: 1.1rem;
  font-weight: bold;
  margin-top: 0;
  margin-bottom: 15px;
  color: #ffffff;
  border-bottom: 1px solid #3f444e;
  padding-bottom: 8px;
}

.section-sub-title {
  font-size: 0.85rem;
  text-transform: uppercase;
  color: #22d3ee;
  margin: 10px 0 12px 0;
  letter-spacing: 0.5px;
}

/* METRICS CARDS */
.metrics-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.metric-card {
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  padding: 14px 18px;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.metric-label {
  color: #aaaaaa;
  font-size: 0.85rem;
  text-transform: uppercase;
}

.metric-value {
  color: #ffffff;
  font-size: 1.1rem;
}

.committee-name {
  font-weight: bold;
  color: #22d3ee;
}

.fraction {
  font-size: 1.2rem;
  color: #aaaaaa;
}

.fraction strong {
  color: #ffffff;
  font-size: 1.4rem;
}

.graded-count {
  color: #22c55e !important;
}

/* TIMELINE */
.timeline-section {
  margin-bottom: 20px;
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background-color: #1a1d21;
  border: 1px solid #3f444e;
  padding: 12px 16px;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.node-indicator {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  background-color: #2a2e35;
  border: 1px solid #3f444e;
  display: flex;
  justify-content: center;
  align-items: center;
  font-weight: bold;
  font-size: 0.8rem;
  color: #888888;
  margin-top: 2px;
}

.timeline-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.event-label {
  font-size: 0.95rem;
  font-weight: bold;
  color: #ffffff;
}

.event-time {
  font-size: 0.8rem;
  color: #888888;
}

.status-pill {
  font-size: 0.7rem;
  font-weight: bold;
  text-transform: uppercase;
  padding: 2px 6px;
  border-radius: 3px;
}

/* TIMELINE STATUS STYLES */
/* Completed */
.timeline-item.completed {
  border-color: #3f444e;
  opacity: 0.8;
}

.timeline-item.completed .node-indicator {
  background-color: #14532d;
  color: #86efac;
  border-color: #22c55e;
}

.timeline-item.completed .status-pill {
  background-color: #14532d;
  color: #86efac;
}

/* Active / In Progress */
.timeline-item.active {
  border-color: #6366f1;
  background-color: #222630;
  box-shadow: 0 0 10px rgba(99, 102, 241, 0.2);
}

.timeline-item.active .node-indicator {
  background-color: #6366f1;
  color: #ffffff;
  border-color: #6366f1;
}

.timeline-item.active .event-label {
  color: #22d3ee;
}

.timeline-item.active .status-pill {
  background-color: #6366f1;
  color: #ffffff;
}

/* Upcoming */
.timeline-item.upcoming .status-pill {
  background-color: #2a2e35;
  color: #aaaaaa;
}

/* RESPONSIVE */
@media (max-width: 900px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
  .toggle-container {
    flex-direction: column;
    align-items: center;
  }
  .toggle-btn {
    width: 100%;
  }
}
</style>