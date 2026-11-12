import { computed, ref } from 'vue'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'
import { toLocalInput, toUtcIso } from '../utils/datetime'

/**
 * Announcements and conference links, shared by the two cards that edit them.
 *
 * The editor card owns the form and the kind toggle; the published-list card renders
 * whichever kind is selected and offers reorder/edit/delete. They are separate cards on the
 * Displays tab but one piece of state, which is why this is a module-level composable rather
 * than props and events: the toggle in the left card has to switch the title and contents of
 * the right one, and reordering has to re-read the same list the editor counts capacity from.
 *
 * Module-level rather than per-call, matching `useSchools`/`useCommitteeNames`: the tab is
 * kept alive, but a remount must not throw away an unsaved draft.
 */

// Mirror of core.controls.BROADCAST_LIMITS in the backend, used to show capacity.
// The backend is still the authority: it returns 409 if a create would overflow.
const broadcastLimits = {
  announcement: { global: 2, committee: 1 },
  link: { global: 2, committee: 3 }
}

const broadcastKinds = [
  { kind: 'announcement', label: 'Announcements' },
  { kind: 'link', label: 'Conference Links' }
]

const broadcastKind = ref('announcement')
const broadcasts = ref([])
const committees = ref([])
const loadingBroadcasts = ref(false)
const savingBroadcast = ref(false)
const editingId = ref(null)

const emptyBroadcast = () => ({
  body: '',
  url: '',
  committee_name: null,
  starts_at: '',
  ends_at: ''
})

const newBroadcast = ref(emptyBroadcast())
const editDraft = ref(emptyBroadcast())

// ---------- Derived ----------
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

// Capacity for every target the form can publish to: the general strip plus one line per
// committee. Listing them all (even at 0/1) is the point - hiding the committees the form was
// not pointing at made the remaining space look like a single shared budget.
const broadcastCapacity = computed(() => {
  const limits = broadcastLimits[broadcastKind.value]
  const selected = newBroadcast.value.committee_name

  const targets = [
    { label: 'All delegates', key: null, limit: limits.global, selected: !selected }
  ]
  committees.value.forEach((committee) => {
    targets.push({
      label: committee,
      key: committee,
      limit: limits.committee,
      selected: selected === committee
    })
  })

  return targets.map((target) => {
    const used = usedFor(broadcastKind.value, target.key)
    return { ...target, used, full: used >= target.limit }
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

// ---------- Actions ----------
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
  const toastStore = useToastStore()
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
  const toastStore = useToastStore()
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
  const toastStore = useToastStore()
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

export function useBroadcasts() {
  return {
    // state
    broadcastKinds,
    broadcastKind,
    broadcasts,
    committees,
    loadingBroadcasts,
    savingBroadcast,
    editingId,
    newBroadcast,
    editDraft,
    // derived
    broadcastsOfKind,
    broadcastBodyLabel,
    broadcastBodyPlaceholder,
    broadcastCapacity,
    targetFull,
    broadcastGroups,
    scheduleLabel,
    stateLabel,
    stateClass,
    canMove,
    // actions
    loadBroadcasts,
    selectBroadcastKind,
    createBroadcast,
    startEdit,
    cancelEdit,
    saveBroadcast,
    moveBroadcast,
    deleteBroadcast
  }
}
