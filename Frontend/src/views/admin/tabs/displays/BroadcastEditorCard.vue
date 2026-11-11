<template>
<div class="section-card">
  <h2>Announcements &amp; Conference Links</h2>
  <p class="section-desc">
    What delegates see on their dashboard: announcements fill the bar at the top
    (up to 3 lines), links fill the five slots in the "Conference &amp; General Info"
    panel. A line addressed to a committee reaches only that committee's delegates,
    and is shown after the general lines.
  </p>

  <div class="toggle-container">
    <button
      v-for="option in broadcastKinds"
      :key="option.kind"
      :class="['toggle-btn', { active: broadcastKind === option.kind }]"
      @click="selectBroadcastKind(option.kind)"
    >
      {{ option.label }}
    </button>
  </div>

  <p class="capacity-line">
    <strong>Space left:</strong>
    <span
      v-for="row in broadcastCapacity"
      :key="row.label"
      :class="['capacity-chip', { full: row.full }]"
    >
      {{ row.label }}: {{ row.used }}/{{ row.limit }}
    </span>
    <span class="capacity-note">
      counted per target, and a line that has not ended yet still holds its place
    </span>
  </p>

  <div class="broadcast-form">
    <label class="field-label" :for="`broadcast-body`">{{ broadcastBodyLabel }}</label>
    <input
      id="broadcast-body"
      v-model="newBroadcast.body"
      class="text-input"
      type="text"
      :placeholder="broadcastBodyPlaceholder"
    />

    <template v-if="broadcastKind === 'link'">
      <label class="field-label" for="broadcast-url">Link URL</label>
      <input
        id="broadcast-url"
        v-model="newBroadcast.url"
        class="text-input"
        type="text"
        placeholder="https://..."
      />
    </template>

    <label class="field-label" for="broadcast-target">Shown to</label>
    <select id="broadcast-target" v-model="newBroadcast.committee_name" class="text-input">
      <option :value="null">All delegates</option>
      <option v-for="committee in committees" :key="committee" :value="committee">
        {{ committee }}
      </option>
    </select>

    <div class="schedule-row">
      <div>
        <label class="field-label" for="broadcast-starts">Starts (optional)</label>
        <input
          id="broadcast-starts"
          v-model="newBroadcast.starts_at"
          class="text-input"
          type="datetime-local"
        />
      </div>
      <div>
        <label class="field-label" for="broadcast-ends">Ends (optional)</label>
        <input
          id="broadcast-ends"
          v-model="newBroadcast.ends_at"
          class="text-input"
          type="datetime-local"
        />
      </div>
    </div>
    <p class="capacity-note">
      Times are your local time. Leave both blank to publish now with no end.
    </p>

    <div class="row-actions">
      <button
        class="btn-refresh"
        :disabled="savingBroadcast || targetFull"
        @click="createBroadcast"
      >
        {{ savingBroadcast ? 'Saving...' : 'Publish' }}
      </button>
      <span v-if="targetFull" class="capacity-warning">
        That target is full — delete one of its lines first.
      </span>
    </div>
  </div>
</div>
</template>

<script setup>
import { onActivated, onDeactivated } from 'vue'
import { useBroadcasts } from '../../composables/useBroadcasts'

// The form half of the delegate display. Its published-list twin reads the same singleton,
// which is what lets this card's Announcements / Conference Links toggle switch that card.
const {
  broadcastKinds,
  broadcastKind,
  broadcasts,
  committees,
  savingBroadcast,
  newBroadcast,
  broadcastBodyLabel,
  broadcastBodyPlaceholder,
  broadcastCapacity,
  targetFull,
  loadBroadcasts,
  selectBroadcastKind,
  createBroadcast,
  editingId
} = useBroadcasts()

// Entry refresh, as the old ContentTab hook did: never refetch a list that is already loaded.
onActivated(() => {
  if (!broadcasts.value.length) loadBroadcasts()
})

// Leaving the tab cancels an in-progress row edit in the list card, which is what switchTab
// used to do; the edit state lives in the shared composable, so it is cleared here.
onDeactivated(() => {
  editingId.value = null
})
</script>
