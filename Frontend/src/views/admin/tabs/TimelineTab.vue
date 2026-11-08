<template>
<div class="section-card">
  <div class="card-header-action">
    <h2>Conference Timeline</h2>
    <button class="btn-refresh" :disabled="loadingTimeline" @click="loadTimeline">
      <AppIcon name="refresh" />
      <span>{{ loadingTimeline ? 'Loading...' : 'Reload' }}</span>
    </button>
  </div>
  <p class="section-desc">
    The schedule every chair sees on their committee overview. Events are
    <strong>points in time</strong> — a chair's dashboard marks each one completed, in
    progress or upcoming by comparing it with the clock, so there is nothing to tick.
    Order does not matter here: the list is sorted by time when it is saved.
    <br><br>
    Take note that the first event is pinned to the conference start, and its time is what the header countdown reads. You cannot remove or change this event except the date.
  </p>

  <div v-if="!timelineEvents.length" class="empty-state">
    No events yet — add the first one below.
  </div>

  <div
    v-for="(event, index) in timelineEvents"
    :key="index"
    class="timeline-editor-row"
    :class="{ 'is-pinned': event.pinned }"
  >
    <select
      v-model="event.phase"
      class="text-input"
      :disabled="event.pinned"
      @change="timelineDirty = true"
    >
      <option v-for="phase in timelinePhases" :key="phase.value" :value="phase.value">
        {{ phase.label }}
      </option>
    </select>
    <input
      v-model="event.label"
      class="text-input"
      type="text"
      :disabled="event.pinned"
      placeholder="e.g. Opening Ceremony"
      @input="timelineDirty = true"
    />
    <input
      v-model="event.starts_at"
      class="text-input"
      type="datetime-local"
      @input="timelineDirty = true"
    />
    <span v-if="event.pinned" class="pinned-note" title="The conference start: the header countdown reads it">
      start
    </span>
    <button v-else class="btn-icon" title="Remove event" @click="removeTimelineEvent(index)">
      <AppIcon name="close" :size="14" />
    </button>
  </div>

  <div class="row-actions">
    <button
      class="btn-secondary"
      :disabled="timelineEvents.length >= maxTimelineEvents"
      @click="addTimelineEvent"
    >
      + Add event
    </button>
    <button
      class="btn-refresh"
      :disabled="savingTimeline || !timelineDirty"
      @click="saveTimeline"
    >
      {{ savingTimeline ? 'Saving...' : 'Save timeline' }}
    </button>
    <span v-if="timelineDirty" class="capacity-warning">Unsaved changes</span>
    <span class="capacity-note">
      {{ timelineEvents.length }}/{{ maxTimelineEvents }} events · times are your local time
    </span>
  </div>
</div>
</template>

<script setup>
import AppIcon from '@/components/AppIcon.vue'
import { onActivated, ref } from 'vue'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'
import { toLocalInput, toUtcIso } from '../utils/datetime'

const toastStore = useToastStore()

// ---------- Timeline state ----------
const timelinePhases = [
  { value: 'preConference', label: 'Pre-conference' },
  { value: 'duringConference', label: 'During conference' }
]
const timelineEvents = ref([])
const loadingTimeline = ref(false)
const savingTimeline = ref(false)
const timelineDirty = ref(false)
const maxTimelineEvents = 30 // mirrors MAX_TIMELINE_EVENTS in admin.py

// ---------- Timeline actions ----------
const loadTimeline = async () => {
  loadingTimeline.value = true
  try {
    const response = await apiClient.get('/admin/timeline')
    // Stored as naive UTC, edited as local wall-clock time.
    timelineEvents.value = (response.data.events || []).map((event) => ({
      id: event.id,
      phase: event.phase,
      label: event.label,
      starts_at: toLocalInput(event.starts_at),
      pinned: Boolean(event.pinned)
    }))
    timelineDirty.value = false
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    loadingTimeline.value = false
  }
}

const addTimelineEvent = () => {
  timelineEvents.value.push({
    id: null,
    phase: 'preConference',
    label: '',
    starts_at: '',
    pinned: false
  })
  timelineDirty.value = true
}

const removeTimelineEvent = (index) => {
  if (timelineEvents.value[index]?.pinned) {
    // Matches the server rule: the start line can be re-dated, never dropped.
    toastStore.showToast(
      'The Conference Start line sets the conference time and cannot be removed. Change its time instead.',
      'error'
    )
    return
  }
  timelineEvents.value.splice(index, 1)
  timelineDirty.value = true
}

const saveTimeline = async () => {
  if (timelineEvents.value.some((event) => !event.label.trim())) {
    toastStore.showToast('Every timeline event needs a label.', 'error')
    return
  }
  if (timelineEvents.value.some((event) => !event.starts_at)) {
    toastStore.showToast('Every timeline event needs a date and time.', 'error')
    return
  }

  savingTimeline.value = true
  try {
    const response = await apiClient.put('/admin/timeline', {
      events: timelineEvents.value.map((event) => ({
        phase: event.phase,
        label: event.label.trim(),
        starts_at: toUtcIso(event.starts_at)
      }))
    })
    // The server returns them sorted by time, which is the order the editor shows.
    timelineEvents.value = (response.data.events || []).map((event) => ({
      id: event.id,
      phase: event.phase,
      label: event.label,
      starts_at: toLocalInput(event.starts_at),
      pinned: Boolean(event.pinned)
    }))
    timelineDirty.value = false
    toastStore.showToast('Timeline saved.', 'success')
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    savingTimeline.value = false
  }
}

// Refreshed on entry, but never over unsaved edits - the same rule the old switchTab had.
onActivated(() => {
  if (!timelineDirty.value) loadTimeline()
})

</script>
