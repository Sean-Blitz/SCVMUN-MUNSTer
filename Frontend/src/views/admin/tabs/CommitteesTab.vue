<template>
<!-- CREATE -->
<div class="section-card">
  <h2>Create a Committee</h2>
  <p class="section-desc">
    A committee has to exist before its delegates can be minted — a delegate's committee
    is no longer created on the fly.
  </p>
  <div class="school-fields">
    <div class="field-pair">
      <label class="field-label" for="new-committee-name">Name</label>
      <input id="new-committee-name" v-model="newCommittee.committee_name" class="text-input" type="text" placeholder="e.g. DISEC" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-committee-type">Type (optional)</label>
      <input id="new-committee-type" v-model="newCommittee.committee_type" class="text-input" type="text" placeholder="e.g. General Assembly" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-committee-topic">Topic (optional)</label>
      <input id="new-committee-topic" v-model="newCommittee.topic" class="text-input" type="text" placeholder="e.g. Nuclear disarmament" />
    </div>
  </div>
  <div class="row-actions">
    <button class="btn-refresh" :disabled="creatingCommittee" @click="createCommittee">
      {{ creatingCommittee ? 'Creating...' : 'Create Committee' }}
    </button>
  </div>
</div>

<!-- PICKER -->
<div class="section-card">
  <h2>Existing Committees</h2>
  <p class="section-desc">Pick a committee to see its chairs and delegates.</p>
  <label class="field-label" for="committee-picker">Committee</label>
  <select id="committee-picker" v-model="selectedCommittee" class="text-input" @change="loadCommitteeDetail">
    <option value="">— choose a committee —</option>
    <option v-for="name in committeeNames" :key="name" :value="name">{{ name }}</option>
  </select>
  <div v-if="!committeeNames.length" class="empty-state">
    No committees yet — create one above.
  </div>
</div>

<!-- DETAILS -->
<div v-if="committeeDetail" class="section-card">
  <div class="card-header-action">
    <h2>{{ committeeDetail.committee_name }}</h2>
    <button class="btn-refresh" :disabled="!committeeDirty || savingCommittee" @click="saveCommittee">
      {{ savingCommittee ? 'Saving...' : 'Save changes' }}
    </button>
  </div>
  <p class="section-desc">
    Renaming repoints every delegate, chair and committee-scoped announcement at the new
    name in one step.
  </p>
  <div class="school-fields">
    <div class="field-pair">
      <label class="field-label" for="edit-committee-name">Name</label>
      <input id="edit-committee-name" v-model="committeeDraft.committee_name" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-committee-type">Type</label>
      <input id="edit-committee-type" v-model="committeeDraft.committee_type" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-committee-topic">Topic</label>
      <input id="edit-committee-topic" v-model="committeeDraft.topic" class="text-input" type="text" />
    </div>
  </div>
</div>

<!-- CHAIRS -->
<div v-if="committeeDetail" class="section-card">
  <h2>Chairs ({{ committeeDetail.chairs.length }})</h2>
  <p class="section-desc">
    Each chair signs up with their hash using "First-Time Register". Reissuing a hash
    invalidates the old one immediately.
  </p>

  <div v-if="!committeeDetail.chairs.length" class="empty-state">No chairs assigned yet.</div>
  <div v-else class="chair-table">
    <div class="chair-head">
      <span>Name</span><span>Email</span><span>Hash</span><span></span>
    </div>
    <div v-for="row in chairDrafts" :key="row.account_id" class="chair-row">
      <input v-model="row.name" class="text-input" type="text" />
      <input v-model="row.email" class="text-input" type="text" />
      <span class="hash-value">{{ row.hash }}</span>
      <div class="delegate-actions">
        <button class="btn-refresh" :disabled="!chairDirty(row) || savingChairId === row.account_id" @click="saveChair(row)">
          {{ savingChairId === row.account_id ? 'Saving...' : 'Save' }}
        </button>
        <button class="btn-copy" @click="copyHash(row.hash)">Copy</button>
        <button class="btn-copy" :disabled="reissuingChairId === row.account_id" @click="reissueChair(row)">
          {{ reissuingChairId === row.account_id ? 'Reissuing...' : 'Reissue' }}
        </button>
        <button class="btn-copy btn-copy-danger" :disabled="removingChairId === row.account_id" @click="removeChair(row)">
          {{ removingChairId === row.account_id ? 'Removing...' : 'Remove' }}
        </button>
      </div>
    </div>
  </div>

  <div class="school-fields chair-add">
    <div class="field-pair">
      <label class="field-label" for="new-chair-name">New chair name</label>
      <input id="new-chair-name" v-model="newChair.name" class="text-input" type="text" placeholder="Jane Doe" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-chair-email">New chair email</label>
      <input id="new-chair-email" v-model="newChair.email" class="text-input" type="text" placeholder="jane@lhs.edu" />
    </div>
  </div>
  <div class="row-actions">
    <button class="btn-refresh" :disabled="addingChair" @click="addChair">
      {{ addingChair ? 'Adding...' : 'Add chair & issue hash' }}
    </button>
  </div>
</div>

<!-- DELEGATES -->
<div v-if="committeeDetail" class="section-card">
  <h2>Delegates ({{ committeeDetail.delegates.length }})</h2>
  <p class="section-desc">
    Country and committee edits live in Existing Schools; here you can reissue a hash or
    remove the delegate from this committee entirely.
  </p>

  <div v-if="!committeeDetail.delegates.length" class="empty-state">
    No delegates in this committee yet.
  </div>
  <div v-else class="delegate-table">
    <div class="delegate-head">
      <span>School</span><span>Country</span><span>Paper</span><span>Hash</span><span></span>
    </div>
    <div v-for="row in committeeDetail.delegates" :key="row.account_id" class="delegate-row committee-row">
      <span class="delegate-label">{{ row.school_name }}</span>
      <span>{{ row.country }}</span>
      <span class="paper-badge" :class="'is-' + row.paper_status">
        {{ row.paper_status }}<template v-if="row.paper_grade"> · {{ row.paper_grade }}</template><template
          v-if="!row.has_paper && row.paper_status !== 'unsubmitted'"
        > (no file)</template>
      </span>
      <span class="hash-value">{{ row.hash }}</span>
      <div class="delegate-actions">
        <button class="btn-copy" @click="copyHash(row.hash)">Copy</button>
        <button class="btn-copy" :disabled="reissuingDelegateId === row.account_id" @click="reissueCommitteeDelegate(row)">
          {{ reissuingDelegateId === row.account_id ? 'Reissuing...' : 'Reissue' }}
        </button>
        <button class="btn-copy btn-copy-danger" :disabled="removingDelegateId === row.account_id" @click="removeCommitteeDelegate(row)">
          {{ removingDelegateId === row.account_id ? 'Removing...' : 'Remove' }}
        </button>
      </div>
    </div>
  </div>
</div>
</template>

<script setup>
import { computed, onActivated, ref } from 'vue'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'
import { useCommitteeNames } from '../composables/useCommitteeNames'
import { useCopyHash } from '../composables/useCopyHash'

const toastStore = useToastStore()
const { committeeNames, loadCommitteeNames } = useCommitteeNames()
const { copyHash } = useCopyHash()

// ---------- Committees: create, rename, chairs, delegate removal ----------
// Also feeds the <datalist> every committee input in the page uses, because a delegate can
// only be minted into a committee that exists.
const selectedCommittee = ref('')
const committeeDetail = ref(null)
const committeeDraft = ref(null)
const chairDrafts = ref([])
const newCommittee = ref({ committee_name: '', committee_type: '', topic: '' })
const creatingCommittee = ref(false)
const savingCommittee = ref(false)
const newChair = ref({ name: '', email: '' })
const addingChair = ref(false)
const savingChairId = ref(null)
const reissuingChairId = ref(null)
const removingChairId = ref(null)
const reissuingDelegateId = ref(null)
const removingDelegateId = ref(null)

const applyCommitteeDetail = (detail) => {
  committeeDetail.value = detail
  committeeDraft.value = {
    committee_name: detail.committee_name,
    committee_type: detail.committee_type || '',
    topic: detail.topic || ''
  }
  chairDrafts.value = (detail.chairs || []).map((chair) => ({ ...chair }))
}

const loadCommitteeDetail = async () => {
  if (!selectedCommittee.value) {
    committeeDetail.value = null
    committeeDraft.value = null
    chairDrafts.value = []
    return
  }
  try {
    const response = await apiClient.get(
      `/admin/committees/${encodeURIComponent(selectedCommittee.value)}`
    )
    applyCommitteeDetail(response.data)
  } catch (error) {
    // toasted by the interceptor
  }
}

const createCommittee = async () => {
  const name = newCommittee.value.committee_name.trim()
  if (!name) {
    toastStore.showToast('Enter a committee name.', 'error')
    return
  }

  creatingCommittee.value = true
  try {
    const response = await apiClient.post('/admin/committees', {
      committee_name: name,
      committee_type: newCommittee.value.committee_type.trim() || null,
      topic: newCommittee.value.topic.trim() || null
    })
    newCommittee.value = { committee_name: '', committee_type: '', topic: '' }
    await loadCommittees()
    selectedCommittee.value = response.data.committee_name
    applyCommitteeDetail(response.data)
    toastStore.showToast('Committee created.', 'success')
  } catch (error) {
    // 409 / 400 / 422 arrive with a message and are toasted by the interceptor
  } finally {
    creatingCommittee.value = false
  }
}

const committeeDirty = computed(() => {
  if (!committeeDetail.value || !committeeDraft.value) return false
  return (
    committeeDraft.value.committee_name.trim() !== committeeDetail.value.committee_name ||
    (committeeDraft.value.committee_type || '') !== (committeeDetail.value.committee_type || '') ||
    (committeeDraft.value.topic || '') !== (committeeDetail.value.topic || '')
  )
})

const saveCommittee = async () => {
  if (!committeeDetail.value || !committeeDraft.value) return
  const changes = {}
  if (committeeDraft.value.committee_name.trim() !== committeeDetail.value.committee_name) {
    changes.committee_name = committeeDraft.value.committee_name.trim()
  }
  if ((committeeDraft.value.committee_type || '') !== (committeeDetail.value.committee_type || '')) {
    changes.committee_type = committeeDraft.value.committee_type.trim() || null
  }
  if ((committeeDraft.value.topic || '') !== (committeeDetail.value.topic || '')) {
    changes.topic = committeeDraft.value.topic.trim() || null
  }

  savingCommittee.value = true
  try {
    const response = await apiClient.patch(
      `/admin/committees/${encodeURIComponent(committeeDetail.value.committee_name)}`,
      changes
    )
    // Keep unsaved chair edits; a rename does not touch them.
    const typed = new Map(chairDrafts.value.map((chair) => [chair.account_id, chair]))
    applyCommitteeDetail(response.data)
    chairDrafts.value = chairDrafts.value.map((fresh) => {
      const row = typed.get(fresh.account_id)
      return row ? { ...fresh, name: row.name, email: row.email } : fresh
    })
    selectedCommittee.value = response.data.committee_name
    await loadCommittees()
    toastStore.showToast('Committee updated.', 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    savingCommittee.value = false
  }
}

const chairDirty = (row) => {
  const original = committeeDetail.value?.chairs.find((c) => c.account_id === row.account_id)
  if (!original) return false
  return row.name.trim() !== original.name || row.email.trim() !== original.email
}

const saveChair = async (row) => {
  if (!committeeDetail.value) return false
  const original = committeeDetail.value.chairs.find((c) => c.account_id === row.account_id)
  if (!original) return false
  const changes = {}
  if (row.name.trim() !== original.name) changes.name = row.name.trim()
  if (row.email.trim() !== original.email) changes.email = row.email.trim()
  if (!Object.keys(changes).length) return true

  savingChairId.value = row.account_id
  try {
    const response = await apiClient.patch(
      `/admin/committees/${encodeURIComponent(committeeDetail.value.committee_name)}/chairs/${row.account_id}`,
      changes
    )
    Object.assign(row, response.data)
    const index = committeeDetail.value.chairs.findIndex((c) => c.account_id === row.account_id)
    if (index !== -1) committeeDetail.value.chairs[index] = { ...response.data }
    toastStore.showToast('Chair updated.', 'success')
    return true
  } catch (error) {
    return false
  } finally {
    savingChairId.value = null
  }
}

const addChair = async () => {
  if (!committeeDetail.value) return
  const name = newChair.value.name.trim()
  const email = newChair.value.email.trim()
  if (!name || !email) {
    toastStore.showToast('Enter the chair name and email.', 'error')
    return
  }

  addingChair.value = true
  try {
    const response = await apiClient.post(
      `/admin/committees/${encodeURIComponent(committeeDetail.value.committee_name)}/chairs`,
      { name, email }
    )
    committeeDetail.value.chairs = [...committeeDetail.value.chairs, response.data]
    chairDrafts.value = [...chairDrafts.value, { ...response.data }]
    newChair.value = { name: '', email: '' }
    toastStore.showToast('Chair added — hand them the hash.', 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    addingChair.value = false
  }
}

const reissueChair = async (row) => {
  if (chairDirty(row) && !(await saveChair(row))) return
  if (!window.confirm(`Reissue ${row.name}'s hash?\n\nThe current hash stops working immediately.`)) {
    return
  }

  reissuingChairId.value = row.account_id
  try {
    const response = await apiClient.post('/admin/hashes/regenerate/chair', {
      account_id: row.account_id
    })
    row.hash = response.data.hash
    const index = committeeDetail.value.chairs.findIndex((c) => c.account_id === row.account_id)
    if (index !== -1) committeeDetail.value.chairs[index].hash = response.data.hash
    toastStore.showToast('Hash reissued.', 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    reissuingChairId.value = null
  }
}

const removeChair = async (row) => {
  if (
    !window.confirm(
      `Remove ${row.name} as a chair of ${committeeDetail.value.committee_name}?\n\nTheir account and hash are deleted.`
    )
  ) {
    return
  }

  removingChairId.value = row.account_id
  try {
    await apiClient.delete(
      `/admin/committees/${encodeURIComponent(committeeDetail.value.committee_name)}/chairs/${row.account_id}`
    )
    committeeDetail.value.chairs = committeeDetail.value.chairs.filter(
      (c) => c.account_id !== row.account_id
    )
    chairDrafts.value = chairDrafts.value.filter((c) => c.account_id !== row.account_id)
    toastStore.showToast('Chair removed.', 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    removingChairId.value = null
  }
}

const reissueCommitteeDelegate = async (row) => {
  if (
    !window.confirm(
      `Reissue the hash for ${row.country} (${row.school_name})?\n\nThe current hash stops working immediately.`
    )
  ) {
    return
  }

  reissuingDelegateId.value = row.account_id
  try {
    const response = await apiClient.post('/admin/hashes/regenerate/delegate', {
      committee: committeeDetail.value.committee_name,
      country: row.country
    })
    row.hash = response.data.hash
    toastStore.showToast('Hash reissued.', 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    reissuingDelegateId.value = null
  }
}

const removeCommitteeDelegate = async (row) => {
  const graded = row.paper_status === 'graded' ? '\n\nThis delegate has a graded paper.' : ''
  if (
    !window.confirm(
      `Remove ${row.country} (${row.school_name}) from ${committeeDetail.value.committee_name}?` +
        '\n\nTheir account, hash and stored paper are deleted.' +
        graded
    )
  ) {
    return
  }

  removingDelegateId.value = row.account_id
  try {
    const response = await apiClient.delete(
      `/admin/committees/${encodeURIComponent(committeeDetail.value.committee_name)}/delegates/${row.account_id}`
    )
    committeeDetail.value.delegates = committeeDetail.value.delegates.filter(
      (d) => d.account_id !== row.account_id
    )
    toastStore.showToast(`${response.data.delegate} removed from the committee.`, 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    removingDelegateId.value = null
  }
}

// Cold-load the dropdown on entry; creating a committee refreshes it explicitly.
onActivated(() => {
  if (!committeeNames.value.length) loadCommitteeNames()
})

</script>
