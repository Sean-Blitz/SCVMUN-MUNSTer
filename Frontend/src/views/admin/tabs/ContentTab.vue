<template>
<!-- EDITOR -->
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

<!-- PUBLISHED LIST -->
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

<!-- CONFERENCE CHECKLIST: SHARED LABELS -->
<div class="section-card">
  <h2>Conference Action Checklist</h2>
  <p class="section-desc">
    The checklist lines shown on <strong>every</strong> advisor's dashboard — the labels
    are shared, the ticks are per school (below). Add, rename or remove lines; Save
    replaces the whole list. Removing a line also removes every school's tick for it.
  </p>

  <p v-if="loadingChecklist" class="section-desc">Loading checklist…</p>

  <template v-else>
    <div v-if="!checklistItems.length" class="empty-state">
      No lines yet — add the first one below.
    </div>

    <div v-for="(item, index) in checklistItems" :key="index" class="checklist-row">
      <input
        v-model="item.label"
        class="text-input"
        type="text"
        placeholder="e.g. Submit position papers"
        @input="checklistDirty = true"
      />
      <button class="btn-icon" title="Remove line" @click="removeChecklistItem(index)">
        <AppIcon name="close" :size="14" />
      </button>
    </div>

    <div class="row-actions">
      <button
        class="btn-secondary"
        :disabled="checklistItems.length >= maxChecklistItems"
        @click="addChecklistItem"
      >
        + Add line
      </button>
      <button
        class="btn-refresh"
        :disabled="savingChecklist || !checklistDirty"
        @click="saveChecklist"
      >
        {{ savingChecklist ? 'Saving...' : 'Save checklist' }}
      </button>
      <span v-if="checklistDirty" class="capacity-warning">Unsaved changes</span>
      <span class="capacity-note">{{ checklistItems.length }}/{{ maxChecklistItems }} lines</span>
    </div>
  </template>
</div>

<!-- CHECKLIST PROGRESS: PER SCHOOL -->
<div class="section-card">
  <h2>Checklist Progress</h2>
  <p class="section-desc">
    Which lines a school has ticked. Pick a school and tick its boxes — a tick here
    shows only on that school's advisor dashboard.
  </p>

  <label class="field-label" for="progress-school">School</label>
  <select
    id="progress-school"
    v-model="progressSchoolId"
    class="text-input"
    @change="onProgressSchoolChange"
  >
    <option :value="null">Select a school…</option>
    <option v-for="school in schools" :key="school.id" :value="school.id">
      {{ school.name }}
    </option>
  </select>

  <template v-if="progressSchoolId !== null">
    <p v-if="loadingProgress" class="section-desc">Loading progress…</p>

    <template v-else>
      <p v-if="!progressItems.length" class="empty-state">
        No checklist lines to tick yet — add some above and save first.
      </p>

      <div v-for="item in progressItems" :key="item.id" class="checklist-row">
        <input
          v-model="item.completed"
          type="checkbox"
          :title="item.completed ? 'Done' : 'Outstanding'"
          @change="progressDirty = true"
        />
        <span class="progress-label">{{ item.label }}</span>
      </div>

      <div class="row-actions">
        <button
          class="btn-refresh"
          :disabled="savingProgress || !progressDirty"
          @click="saveProgress"
        >
          {{ savingProgress ? 'Saving...' : 'Save progress' }}
        </button>
        <span v-if="progressDirty" class="capacity-warning">Unsaved changes</span>
        <span class="capacity-note">{{ progressDone }}/{{ progressItems.length }} ticked</span>
      </div>
    </template>
  </template>
</div>
</template>

<script setup>
import AppIcon from '@/components/AppIcon.vue'
import { computed, onActivated, onDeactivated, ref } from 'vue'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'
import { useSchools } from '../composables/useSchools'
import { toLocalInput, toUtcIso } from '../utils/datetime'

const toastStore = useToastStore()
const { schools, loadSchools } = useSchools()

// ---------- Announcements & conference links state ----------
const broadcastKinds = [
  { kind: 'announcement', label: 'Announcements' },
  { kind: 'link', label: 'Conference Links' }
]

// Mirror of core.controls.BROADCAST_LIMITS in the backend, used to show capacity.
// The backend is still the authority: it returns 409 if a create would overflow.
const broadcastLimits = {
  announcement: { global: 2, committee: 1 },
  link: { global: 2, committee: 3 }
}

const broadcastKind = ref('announcement')
const broadcasts = ref([])
const committees = ref([])
const loadingBroadcasts = ref(false)
const savingBroadcast = ref(false)
const editingId = ref(null)

const emptyBroadcast = () => ({ body: '', url: '', committee_name: null, starts_at: '', ends_at: '' })
const newBroadcast = ref(emptyBroadcast())
const editDraft = ref(emptyBroadcast())

// ---------- Conference checklist state (shared labels) ----------
const checklistItems = ref([])
const loadingChecklist = ref(false)
const savingChecklist = ref(false)
const checklistDirty = ref(false)
const maxChecklistItems = 20 // mirrors MAX_CHECKLIST_ITEMS in admin.py

// ---------- Checklist progress state (per school) ----------
const progressSchoolId = ref(null)
const savedProgressSchoolId = ref(null) // the school the tick draft belongs to
const progressItems = ref([])
const loadingProgress = ref(false)
const savingProgress = ref(false)
const progressDirty = ref(false)

const progressDone = computed(
  () => progressItems.value.filter((item) => item.completed).length
)

// ---------- Broadcast computed ----------
const broadcastsOfKind = computed(() =>
  broadcasts.value.filter((row) => row.kind === broadcastKind.value)
)

const broadcastBodyLabel = computed(() =>
  broadcastKind.value === 'link' ? 'Link label' : 'Announcement text'
)

const broadcastBodyPlaceholder = computed(() =>
  broadcastKind.value === 'link'
    ? 'e.g. Conference schedule'
    : 'e.g. Buses depart the hotel at 7:30am'
)

// Rows that can still be shown: one that has already ended releases its place.
const countsTowardCapacity = (row) => !row.ends_at || Date.parse(`${row.ends_at}Z`) > Date.now()

const usedFor = (kind, committeeName) =>
  broadcasts.value.filter(
    (row) =>
      row.kind === kind &&
      (row.committee_name ?? null) === (committeeName ?? null) &&
      countsTowardCapacity(row)
  ).length

// Capacity for the general target plus whichever target the form is pointing at.
const broadcastCapacity = computed(() => {
  const limits = broadcastLimits[broadcastKind.value]
  const targets = [{ label: 'All delegates', key: null, limit: limits.global }]
  const selected = newBroadcast.value.committee_name
  if (selected) {
    targets.push({ label: selected, key: selected, limit: limits.committee })
  }
  return targets.map((target) => {
    const used = usedFor(broadcastKind.value, target.key)
    return { label: target.label, used, limit: target.limit, full: used >= target.limit }
  })
})

const targetFull = computed(() => {
  const limits = broadcastLimits[broadcastKind.value]
  const selected = newBroadcast.value.committee_name
  const limit = selected ? limits.committee : limits.global
  return usedFor(broadcastKind.value, selected) >= limit
})

// One group per target, so reordering only competes with lines the delegate sees together.
const broadcastGroups = computed(() => {
  const byPosition = (a, b) => a.position - b.position || a.id - b.id
  const rows = broadcastsOfKind.value
  const groups = []

  const general = rows.filter((row) => !row.committee_name).sort(byPosition)
  if (general.length) groups.push({ label: 'All delegates', rows: general })

  committees.value.forEach((committee) => {
    const targeted = rows.filter((row) => row.committee_name === committee).sort(byPosition)
    if (targeted.length) groups.push({ label: committee, rows: targeted })
  })

  const known = new Set([null, ...committees.value])
  const orphans = rows.filter((row) => !known.has(row.committee_name)).sort(byPosition)
  if (orphans.length) groups.push({ label: 'Other committees', rows: orphans })

  return groups
})

const formatLocal = (iso) => {
  if (!iso) return ''
  const date = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

const scheduleLabel = (row) =>
  `${row.starts_at ? `from ${formatLocal(row.starts_at)}` : 'from now'} · ${
    row.ends_at ? `until ${formatLocal(row.ends_at)}` : 'no end'
  }`

const stateLabel = (row) => {
  const now = Date.now()
  if (row.ends_at && Date.parse(`${row.ends_at}Z`) <= now) return 'Ended'
  if (row.starts_at && Date.parse(`${row.starts_at}Z`) > now) return 'Scheduled'
  return 'Live'
}

const stateClass = (row) => stateLabel(row).toLowerCase()

const nextPosition = (kind, committeeName) => {
  const group = broadcasts.value.filter(
    (row) => row.kind === kind && (row.committee_name ?? null) === (committeeName ?? null)
  )
  return group.length ? Math.max(...group.map((row) => row.position)) + 1 : 0
}

const groupOf = (row) =>
  broadcasts.value
    .filter(
      (other) =>
        other.kind === row.kind && (other.committee_name ?? null) === (row.committee_name ?? null)
    )
    .sort((a, b) => a.position - b.position || a.id - b.id)

const canMove = (row, delta) => {
  const group = groupOf(row)
  const index = group.findIndex((other) => other.id === row.id)
  return index + delta >= 0 && index + delta < group.length
}

// ---------- Broadcast actions ----------
const loadBroadcasts = async () => {
  loadingBroadcasts.value = true
  try {
    const [listResponse, committeeResponse] = await Promise.all([
      apiClient.get('/admin/broadcasts'),
      apiClient.get('/admin/committees')
    ])
    broadcasts.value = listResponse.data.broadcasts || []
    committees.value = committeeResponse.data || []
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    loadingBroadcasts.value = false
  }
}

const selectBroadcastKind = (kind) => {
  broadcastKind.value = kind
  editingId.value = null
  newBroadcast.value = emptyBroadcast()
}

const createBroadcast = async () => {
  if (!newBroadcast.value.body.trim()) {
    toastStore.showToast('Enter the text before publishing.', 'error')
    return
  }

  savingBroadcast.value = true
  try {
    await apiClient.post('/admin/broadcasts', {
      kind: broadcastKind.value,
      body: newBroadcast.value.body,
      url: broadcastKind.value === 'link' ? newBroadcast.value.url : null,
      committee_name: newBroadcast.value.committee_name,
      position: nextPosition(broadcastKind.value, newBroadcast.value.committee_name),
      starts_at: toUtcIso(newBroadcast.value.starts_at),
      ends_at: toUtcIso(newBroadcast.value.ends_at)
    })
    newBroadcast.value = emptyBroadcast()
    toastStore.showToast('Published.', 'success')
    await loadBroadcasts()
  } catch (error) {
    // 409 (target full) and validation errors pop up via the interceptor
  } finally {
    savingBroadcast.value = false
  }
}

const startEdit = (row) => {
  editingId.value = row.id
  editDraft.value = {
    body: row.body,
    url: row.url || '',
    committee_name: row.committee_name,
    starts_at: toLocalInput(row.starts_at),
    ends_at: toLocalInput(row.ends_at)
  }
}

const cancelEdit = () => {
  editingId.value = null
  editDraft.value = emptyBroadcast()
}

const saveBroadcast = async (row) => {
  savingBroadcast.value = true
  try {
    await apiClient.patch(`/admin/broadcasts/${row.id}`, {
      body: editDraft.value.body,
      url: row.kind === 'link' ? editDraft.value.url : null,
      committee_name: editDraft.value.committee_name,
      starts_at: toUtcIso(editDraft.value.starts_at),
      ends_at: toUtcIso(editDraft.value.ends_at)
    })
    cancelEdit()
    toastStore.showToast('Saved.', 'success')
    await loadBroadcasts()
  } catch (error) {
    // Backend errors pop up via the interceptor
  } finally {
    savingBroadcast.value = false
  }
}

const moveBroadcast = async (row, delta) => {
  const group = groupOf(row)
  const index = group.findIndex((other) => other.id === row.id)
  const swapWith = index + delta
  if (swapWith < 0 || swapWith >= group.length) return

  ;[group[index], group[swapWith]] = [group[swapWith], group[index]]

  savingBroadcast.value = true
  try {
    // Renumber the whole group so equal positions cannot leave the order ambiguous.
    await Promise.all(
      group.map((entry, position) =>
        apiClient.patch(`/admin/broadcasts/${entry.id}`, { position })
      )
    )
    await loadBroadcasts()
  } catch (error) {
    // Backend errors pop up via the interceptor
  } finally {
    savingBroadcast.value = false
  }
}

const deleteBroadcast = async (row) => {
  if (!window.confirm(`Delete "${row.body}"? This cannot be undone.`)) return

  savingBroadcast.value = true
  try {
    await apiClient.delete(`/admin/broadcasts/${row.id}`)
    toastStore.showToast('Deleted.', 'success')
    await loadBroadcasts()
  } catch (error) {
    // Backend errors pop up via the interceptor
  } finally {
    savingBroadcast.value = false
  }
}

// ---------- Conference checklist actions (shared labels) ----------
const loadChecklist = async () => {
  loadingChecklist.value = true
  try {
    const response = await apiClient.get('/admin/checklist')
    // Keep the ids: they are what the schools' ticks point at, so they must be sent back.
    checklistItems.value = (response.data.items || []).map((item) => ({
      id: item.id,
      label: item.label
    }))
    checklistDirty.value = false
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    loadingChecklist.value = false
  }
}

const addChecklistItem = () => {
  checklistItems.value.push({ id: null, label: '' }) // id null = a new line
  checklistDirty.value = true
}

const removeChecklistItem = (index) => {
  checklistItems.value.splice(index, 1)
  checklistDirty.value = true
}

const saveChecklist = async () => {
  if (checklistItems.value.some((item) => !item.label.trim())) {
    toastStore.showToast('Every checklist line needs a label.', 'error')
    return
  }

  savingChecklist.value = true
  try {
    const response = await apiClient.put('/admin/checklist', {
      items: checklistItems.value.map((item) => ({
        id: item.id,
        label: item.label.trim()
      }))
    })
    checklistItems.value = (response.data.items || []).map((item) => ({
      id: item.id,
      label: item.label
    }))
    checklistDirty.value = false
    toastStore.showToast('Checklist saved.', 'success')

    // Line ids may have been added or removed, so re-read the progress view rather than
    // keep ticking against a stale list.
    if (progressSchoolId.value !== null) {
      await loadProgress()
    }
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    savingChecklist.value = false
  }
}

const loadProgress = async () => {
  if (progressSchoolId.value === null) {
    progressItems.value = []
    savedProgressSchoolId.value = null
    progressDirty.value = false
    return
  }

  loadingProgress.value = true
  try {
    const response = await apiClient.get(`/admin/schools/${progressSchoolId.value}/checklist`)
    progressItems.value = (response.data.items || []).map((item) => ({
      id: item.id,
      label: item.label,
      completed: item.completed
    }))
    savedProgressSchoolId.value = progressSchoolId.value
    progressDirty.value = false
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    loadingProgress.value = false
  }
}

// Switching schools throws the tick draft away, so ask first and put the picker back.
const onProgressSchoolChange = async () => {
  if (progressDirty.value && !window.confirm('Discard the unsaved progress changes?')) {
    progressSchoolId.value = savedProgressSchoolId.value
    return
  }
  await loadProgress()
}

const saveProgress = async () => {
  if (progressSchoolId.value === null) return

  savingProgress.value = true
  try {
    const response = await apiClient.patch(`/admin/schools/${progressSchoolId.value}/checklist`, {
      items: progressItems.value.map((item) => ({
        id: item.id,
        completed: item.completed
      }))
    })
    progressItems.value = (response.data.items || []).map((item) => ({
      id: item.id,
      label: item.label,
      completed: item.completed
    }))
    progressDirty.value = false
    toastStore.showToast('Progress saved.', 'success')
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    savingProgress.value = false
  }
}

// Entry refresh, with the old switchTab's guards: never refetch a list that is already
// loaded, and never overwrite a draft the admin has not saved.
onActivated(() => {
  if (!broadcasts.value.length) loadBroadcasts()
  if (!checklistDirty.value) loadChecklist()
  if (!schools.value.length) loadSchools()
})

// Leaving the tab cancels an in-progress broadcast edit, which is what switchTab used to do.
onDeactivated(() => {
  editingId.value = null
})

</script>
