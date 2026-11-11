<template>
<div class="section-card">
  <div class="card-header-action">
    <h2>{{ broadcastKind === 'link' ? 'Conference Links' : 'Announcements' }}</h2>
    <button class="btn-refresh" :disabled="loadingBroadcasts" @click="loadBroadcasts">
      <AppIcon name="refresh" />
      <span>{{ loadingBroadcasts ? 'Loading...' : 'Reload' }}</span>
    </button>
  </div>
  <p class="section-desc">
    Use the arrow buttons to reorder within a target. General lines are always shown before
    committee lines, whatever their position.
  </p>

  <div v-if="!broadcastsOfKind.length" class="empty-state">
    Nothing published yet.
  </div>

  <div v-for="group in broadcastGroups" :key="group.label" class="broadcast-group">
    <h3>{{ group.label }}</h3>

    <div
      v-for="row in group.rows"
      :key="row.id"
      :class="['broadcast-row', { editing: editingId === row.id }]"
    >
      <!-- EDIT MODE -->
      <template v-if="editingId === row.id">
        <input v-model="editDraft.body" class="text-input" type="text" />
        <input
          v-if="row.kind === 'link'"
          v-model="editDraft.url"
          class="text-input"
          type="text"
          placeholder="https://..."
        />
        <select v-model="editDraft.committee_name" class="text-input">
          <option :value="null">All delegates</option>
          <option v-for="committee in committees" :key="committee" :value="committee">
            {{ committee }}
          </option>
        </select>
        <div class="schedule-row">
          <input v-model="editDraft.starts_at" class="text-input" type="datetime-local" />
          <input v-model="editDraft.ends_at" class="text-input" type="datetime-local" />
        </div>
        <div class="row-actions">
          <button class="btn-refresh" :disabled="savingBroadcast" @click="saveBroadcast(row)">
            {{ savingBroadcast ? 'Saving...' : 'Save' }}
          </button>
          <button class="btn-secondary" @click="cancelEdit">Cancel</button>
        </div>
      </template>

      <!-- READ MODE -->
      <template v-else>
        <div class="broadcast-main">
          <span class="broadcast-body">{{ row.body }}</span>
          <span v-if="row.url" class="broadcast-url">{{ row.url }}</span>
          <span class="broadcast-schedule">{{ scheduleLabel(row) }}</span>
        </div>
        <span :class="['broadcast-state', stateClass(row)]">{{ stateLabel(row) }}</span>
        <div class="broadcast-actions">
          <button
            class="btn-icon"
            title="Move up"
            :disabled="!canMove(row, -1) || savingBroadcast"
            @click="moveBroadcast(row, -1)"
          >
            <AppIcon name="up" :size="14" />
          </button>
          <button
            class="btn-icon"
            title="Move down"
            :disabled="!canMove(row, 1) || savingBroadcast"
            @click="moveBroadcast(row, 1)"
          >
            <AppIcon name="down" :size="14" />
          </button>
          <button class="btn-secondary" @click="startEdit(row)">Edit</button>
          <button class="btn-danger" :disabled="savingBroadcast" @click="deleteBroadcast(row)">
            Delete
          </button>
        </div>
      </template>
    </div>
  </div>
</div>
</template>

<script setup>
import AppIcon from '@/components/AppIcon.vue'
import { useBroadcasts } from '../../composables/useBroadcasts'

// The published half. Same composable as the editor card, so the kind toggle on the left
// switches this list's title and contents without any prop plumbing.
const {
  broadcastKind,
  broadcastsOfKind,
  committees,
  loadingBroadcasts,
  savingBroadcast,
  editingId,
  editDraft,
  broadcastGroups,
  scheduleLabel,
  stateLabel,
  stateClass,
  canMove,
  loadBroadcasts,
  startEdit,
  cancelEdit,
  saveBroadcast,
  moveBroadcast,
  deleteBroadcast
} = useBroadcasts()
</script>
