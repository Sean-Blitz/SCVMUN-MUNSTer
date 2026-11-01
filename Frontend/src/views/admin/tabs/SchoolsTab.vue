<template>
<!-- Committee names, offered to every committee field in the page. A delegate can only
     be minted into a committee that exists, so the form suggests the real ones. -->
<datalist id="committee-names">
  <option v-for="name in committeeNames" :key="name" :value="name"></option>
</datalist>

<!-- CREATE A SCHOOL (and its advisor account) -->
<div class="section-card">
  <h2>Create a School</h2>
  <p class="section-desc">
    Creates the school and its advisor account, and issues the advisor's login hash. The
    advisor claims it with "First-Time Register", exactly as a delegate does. Delegate
    hashes can be generated below once the school exists.
  </p>

  <div class="school-fields">
    <div class="field-pair">
      <label class="field-label" for="new-school-name">School name</label>
      <input id="new-school-name" v-model="newSchool.school_name" class="text-input" type="text" placeholder="e.g. Lincoln High School" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-school-address">Address</label>
      <input id="new-school-address" v-model="newSchool.school_address" class="text-input" type="text" placeholder="1 Main St" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-school-city">City</label>
      <input id="new-school-city" v-model="newSchool.city" class="text-input" type="text" placeholder="San Jose" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-school-state">State</label>
      <input id="new-school-state" v-model="newSchool.state" class="text-input" type="text" placeholder="CA" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-school-zip">ZIP</label>
      <input id="new-school-zip" v-model="newSchool.zip_code" class="text-input" type="text" placeholder="95112" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-school-payment">Payment status</label>
      <select id="new-school-payment" v-model="newSchool.payment_status" class="text-input">
        <option value="unpaid">unpaid</option>
        <option value="partially paid">partially paid</option>
        <option value="paid">paid</option>
      </select>
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-school-advisor">Advisor name</label>
      <input id="new-school-advisor" v-model="newSchool.advisor_name" class="text-input" type="text" placeholder="Jane Doe" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-school-advisor-email">Advisor email</label>
      <input id="new-school-advisor-email" v-model="newSchool.advisor_email" class="text-input" type="text" placeholder="jane@school.edu" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-school-advisor-phone">Advisor phone</label>
      <input id="new-school-advisor-phone" v-model="newSchool.advisor_phone" class="text-input" type="text" placeholder="555-0100" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-school-head">Head delegate</label>
      <input id="new-school-head" v-model="newSchool.head_delegate_name" class="text-input" type="text" placeholder="Alex Smith" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-school-head-email">Head delegate email</label>
      <input id="new-school-head-email" v-model="newSchool.head_delegate_email" class="text-input" type="text" placeholder="alex@school.edu" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="new-school-head-phone">Head delegate phone</label>
      <input id="new-school-head-phone" v-model="newSchool.head_delegate_phone" class="text-input" type="text" placeholder="555-0101" />
    </div>
  </div>

  <div class="row-actions">
    <button class="btn-refresh" :disabled="creatingSchool" @click="createSchool">
      {{ creatingSchool ? 'Creating...' : 'Create School & Issue Advisor Hash' }}
    </button>
  </div>

  <div v-if="createdSchool" class="hash-result">
    <h3>Advisor hash for {{ createdSchool.name }}</h3>
    <div class="hash-row">
      <span class="hash-name">{{ createdSchool.name }} — advisor</span>
      <span class="hash-value">{{ createdSchool.advisor_hash }}</span>
      <button class="btn-copy" @click="copyHash(createdSchool.advisor_hash)">Copy</button>
    </div>
    <p class="section-desc">
      Give this to the advisor. It is shown again in the school list below, and it cannot
      be reissued from here.
    </p>
  </div>

  <div v-if="schools.length" class="school-list">
    <h3>Schools</h3>
    <div v-for="school in schools" :key="school.id" class="school-block">
      <div class="hash-row">
        <span class="hash-name">{{ school.name }}</span>
        <span class="hash-value">{{ school.advisor_hash || 'no advisor hash' }}</span>
        <button v-if="school.advisor_hash" class="btn-copy" @click="copyHash(school.advisor_hash)">Copy</button>
        <button
          class="btn-copy"
          :disabled="generatingForSchool === school.id"
          title="Mints a hash for each delegate row you filled in below, for this school"
          @click="generateHashesForSchool(school)"
        >
          {{ generatingForSchool === school.id ? 'Generating…' : 'Issue delegate hashes' }}
        </button>
      </div>
      <div v-if="delegateHashesBySchool[school.id]" class="hash-result">
        <div v-for="entry in delegateHashesBySchool[school.id]" :key="entry.name" class="hash-row">
          <span class="hash-name">{{ entry.name }}</span>
          <span class="hash-value">{{ entry.hash }}</span>
          <button class="btn-copy" @click="copyHash(entry.hash)">Copy</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- GENERATE DELEGATE HASHES -->
<div class="section-card">
  <h2>Generate Hashes for New Delegates</h2>
  <p class="section-desc">
    Register delegates for a school. Each row becomes an account and receives its own login hash.
  </p>

  <label class="field-label" for="school-name">School name</label>
  <input
    id="school-name"
    v-model="schoolName"
    class="text-input"
    type="text"
    placeholder="e.g. Lincoln High School"
  />

  <div class="form-rows">
    <div v-for="(row, index) in newDelegates" :key="index" class="form-row">
      <input v-model="row.committee" class="text-input" type="text" placeholder="Committee" list="committee-names" />
      <input v-model="row.committeeType" class="text-input" type="text" placeholder="Committee type" />
      <input v-model="row.country" class="text-input" type="text" placeholder="Country" />
      <button class="btn-icon" title="Remove row" @click="removeDelegateRow(index)">✕</button>
    </div>
  </div>

  <div class="row-actions">
    <button class="btn-secondary" @click="addDelegateRow">+ Add delegate</button>
    <button class="btn-refresh" :disabled="generatingHashes" @click="generateHashes">
      {{ generatingHashes ? 'Generating...' : 'Generate Hashes' }}
    </button>
  </div>

  <div v-if="generatedHashes.length" class="hash-result">
    <h3>New Hashes</h3>
    <div v-for="entry in generatedHashes" :key="entry.name" class="hash-row">
      <span class="hash-name">{{ entry.name }}</span>
      <span class="hash-value">{{ entry.hash }}</span>
      <button class="btn-copy" @click="copyHash(entry.hash)">Copy</button>
    </div>
  </div>
</div>

<!-- PICKER -->
<div class="section-card">
  <h2>Existing Schools</h2>
  <p class="section-desc">
    Pick a school to see and edit everything attached to it. Only the selected school's
    data is loaded.
  </p>
  <label class="field-label" for="existing-school">School</label>
  <select
    id="existing-school"
    v-model="selectedSchoolId"
    class="text-input"
    @change="loadSchoolDetail"
  >
    <option :value="null">— choose a school —</option>
    <option v-for="school in schools" :key="school.id" :value="school.id">
      {{ school.name }}
    </option>
  </select>
  <div v-if="!schools.length" class="empty-state">
    No schools yet. Create one above.
  </div>
</div>

<!-- SCHOOL DETAILS -->
<div v-if="schoolDetail" class="section-card">
  <div class="card-header-action">
    <h2>{{ schoolDetail.school.school_name }}</h2>
    <button
      class="btn-refresh"
      :disabled="!schoolDirty || savingSchool"
      @click="saveSchool"
    >
      {{ savingSchool ? 'Saving...' : 'Save changes' }}
    </button>
  </div>
  <p class="section-desc">
    Every field below is editable. The advisor hash is shown for reference; delegate
    hashes are reissued rather than typed.
  </p>

  <div class="school-fields">
    <div class="field-pair">
      <label class="field-label" for="edit-school-name">School name</label>
      <input id="edit-school-name" v-model="schoolDraft.school_name" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-school-address">Address</label>
      <input id="edit-school-address" v-model="schoolDraft.school_address" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-school-city">City</label>
      <input id="edit-school-city" v-model="schoolDraft.city" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-school-state">State</label>
      <input id="edit-school-state" v-model="schoolDraft.state" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-school-zip">ZIP</label>
      <input id="edit-school-zip" v-model="schoolDraft.zip_code" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-school-payment">Payment status</label>
      <select id="edit-school-payment" v-model="schoolDraft.payment_status" class="text-input">
        <option value="unpaid">unpaid</option>
        <option value="partially paid">partially paid</option>
        <option value="paid">paid</option>
      </select>
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-school-advisor">Advisor name</label>
      <input id="edit-school-advisor" v-model="schoolDraft.advisor_name" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-school-advisor-email">Advisor email</label>
      <input id="edit-school-advisor-email" v-model="schoolDraft.advisor_email" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-school-advisor-phone">Advisor phone</label>
      <input id="edit-school-advisor-phone" v-model="schoolDraft.advisor_phone" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-school-head">Head delegate</label>
      <input id="edit-school-head" v-model="schoolDraft.head_delegate_name" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-school-head-email">Head delegate email</label>
      <input id="edit-school-head-email" v-model="schoolDraft.head_delegate_email" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-school-head-phone">Head delegate phone</label>
      <input id="edit-school-head-phone" v-model="schoolDraft.head_delegate_phone" class="text-input" type="text" />
    </div>
    <div class="field-pair">
      <label class="field-label" for="edit-school-invoice">Invoice URL (optional)</label>
      <input id="edit-school-invoice" v-model="schoolDraft.invoiceURL" class="text-input" type="text" />
    </div>
  </div>

  <div class="hash-row">
    <span class="hash-name">Advisor hash</span>
    <span class="hash-value">{{ schoolDetail.advisor_hash || '—' }}</span>
    <button
      v-if="schoolDetail.advisor_hash"
      class="btn-copy"
      @click="copyHash(schoolDetail.advisor_hash)"
    >
      Copy
    </button>
  </div>

  <div class="row-actions">
    <button class="btn-danger" :disabled="deletingSchool" @click="deleteSchool">
      {{ deletingSchool ? 'Deleting...' : 'Delete this school' }}
    </button>
  </div>
</div>

<!-- DELEGATES -->
<div v-if="schoolDetail" class="section-card">
  <h2>Delegates ({{ schoolDetail.delegates.length }})</h2>
  <p class="section-desc">
    Country and committee are editable — Save applies them. Reissuing a hash replaces the
    old one immediately.
  </p>

  <div v-if="!schoolDetail.delegates.length" class="empty-state">
    This school has no delegates yet.
  </div>
  <div v-else class="delegate-table">
    <div class="delegate-head">
      <span>Label</span>
      <span>Country</span>
      <span>Committee</span>
      <span>Paper</span>
      <span>Hash</span>
      <span></span>
    </div>
    <div v-for="row in delegateDrafts" :key="row.account_id" class="delegate-row">
      <span class="delegate-label">{{ row.name }}</span>
      <input v-model="row.country" class="text-input" type="text" />
      <input v-model="row.committee" class="text-input" type="text" />
      <span class="paper-badge" :class="'is-' + row.paper_status">
        {{ row.paper_status }}<template v-if="row.paper_grade"> · {{ row.paper_grade }}</template><template
          v-if="!row.has_paper && row.paper_status !== 'unsubmitted'"
        > (no file)</template>
      </span>
      <span class="hash-value">{{ row.hash }}</span>
      <div class="delegate-actions">
        <button
          class="btn-refresh"
          :disabled="!delegateDirty(row) || savingDelegateId === row.account_id"
          @click="saveDelegate(row)"
        >
          {{ savingDelegateId === row.account_id ? 'Saving...' : 'Save' }}
        </button>
        <button
          class="btn-copy"
          :disabled="reissuingId === row.account_id"
          @click="reissueHash(row)"
        >
          {{ reissuingId === row.account_id ? 'Reissuing...' : 'Reissue hash' }}
        </button>
      </div>
    </div>
  </div>
</div>
<!-- ALL HASHES (the old "Look Up Hashes" card, minus the filter) -->
<div class="section-card">
  <div class="card-header-action">
    <h2>All Hashes</h2>
    <button class="btn-refresh" :disabled="loadingAllHashes" @click="loadAllHashes">
      {{ loadingAllHashes ? 'Loading...' : '🔄 Load all hashes' }}
    </button>
  </div>
  <p class="section-desc">
    Every delegate hash on one list, for a handout or a spot check. Individual hashes are
    reissued per delegate under Existing Schools above.
  </p>
  <div v-if="allHashes.length" class="hash-result">
    <div v-for="entry in allHashes" :key="entry.name" class="hash-row">
      <span class="hash-name">{{ entry.name }}</span>
      <span class="hash-value">{{ entry.hash }}</span>
      <button class="btn-copy" @click="copyHash(entry.hash)">Copy</button>
    </div>
  </div>
  <div v-else class="empty-state">
    {{ loadingAllHashes ? 'Loading hashes…' : 'No hashes loaded yet.' }}
  </div>
</div>
</template>

<script setup>
import { computed, onActivated, ref } from 'vue'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'
import { useCommitteeNames } from '../composables/useCommitteeNames'
import { useCopyHash } from '../composables/useCopyHash'
import { useSchools } from '../composables/useSchools'

const toastStore = useToastStore()
const { schools, loadSchools } = useSchools()
const { committeeNames, loadCommitteeNames } = useCommitteeNames()
const { copyHash } = useCopyHash()

// ---------- Hash management state ----------
const schoolName = ref('')

// ---------- Create a school (POST /admin/schools) ----------
const emptySchool = () => ({
  school_name: '',
  school_address: '',
  city: '',
  state: '',
  zip_code: '',
  payment_status: 'unpaid',
  advisor_name: '',
  advisor_email: '',
  advisor_phone: '',
  head_delegate_name: '',
  head_delegate_email: '',
  head_delegate_phone: ''
})

const newSchool = ref(emptySchool())
const creatingSchool = ref(false)
const createdSchool = ref(null)

// Per-school delegate hashes, keyed by school id, plus which row is mid-request.
const delegateHashesBySchool = ref({})
const generatingForSchool = ref(null)

const createSchool = async () => {
  const required = [
    ['school_name', 'school name'],
    ['school_address', 'address'],
    ['city', 'city'],
    ['state', 'state'],
    ['zip_code', 'ZIP code'],
    ['advisor_name', 'advisor name'],
    ['advisor_email', 'advisor email'],
    ['advisor_phone', 'advisor phone'],
    ['head_delegate_name', 'head delegate name'],
    ['head_delegate_email', 'head delegate email'],
    ['head_delegate_phone', 'head delegate phone']
  ]
  const missing = required.filter(([key]) => !String(newSchool.value[key] || '').trim())
  if (missing.length) {
    toastStore.showToast(
      `Please fill in: ${missing.map(([, label]) => label).join(', ')}.`,
      'error'
    )
    return
  }

  creatingSchool.value = true
  try {
    const response = await apiClient.post('/admin/schools', newSchool.value)
    createdSchool.value = response.data
    newSchool.value = emptySchool()
    // The school must show up in the progress picker and in the list above.
    await loadSchools()
    toastStore.showToast(`${response.data.name} created — advisor hash issued.`, 'success')
  } catch (error) {
    // 409 for a duplicate name and the 400s come through the global toast interceptor
  } finally {
    creatingSchool.value = false
  }
}
const newDelegates = ref([{ committee: '', committeeType: '', country: '' }])
const generatingHashes = ref(false)
const generatedHashes = ref([])

const allHashes = ref([])
const loadingAllHashes = ref(false)

// ---------- Hash management actions ----------
const addDelegateRow = () => {
  newDelegates.value.push({ committee: '', committeeType: '', country: '' })
}

const removeDelegateRow = (index) => {
  if (newDelegates.value.length === 1) {
    newDelegates.value[0] = { committee: '', committeeType: '', country: '' }
    return
  }
  newDelegates.value.splice(index, 1)
}

// The delegate rows entered in the card below, keyed by position ("1", "2"); each value is
// [committee, type, country]. The school travels separately as `school_name`, and the
// backend labels every entry "<school> - #<n>" for display. Shared by both entry points so
// there is one definition of what gets submitted.
const buildAssignments = () => {
  const finalAssignments = {}
  newDelegates.value.forEach((row, index) => {
    if (!row.committee.trim() && !row.committeeType.trim() && !row.country.trim()) return
    finalAssignments[`${index + 1}`] = [
      row.committee.trim(),
      row.committeeType.trim(),
      row.country.trim()
    ]
  })
  return finalAssignments
}

// POST /admin/hashes for one school name. Returns null when there is nothing to send, so
// callers can bail without treating it as an error; real failures throw.
const requestHashes = async (school) => {
  const finalAssignments = buildAssignments()
  if (Object.keys(finalAssignments).length === 0) {
    toastStore.showToast('Add at least one delegate row first.', 'error')
    return null
  }
  const response = await apiClient.post('/admin/hashes', { school_name: school, finalAssignments })
  return response.data.hashes || []
}

const generateHashes = async () => {
  const school = schoolName.value.trim()
  if (!school) {
    toastStore.showToast('Enter a school name before generating hashes.', 'error')
    return
  }

  generatingHashes.value = true
  try {
    const hashes = await requestHashes(school)
    if (hashes === null) return
    generatedHashes.value = hashes
    toastStore.showToast('Hashes generated.', 'success')
  } catch (error) {
    // Errors automatically pop up via global toast interceptor
  } finally {
    generatingHashes.value = false
  }
}

// Issued from the school list: the school name comes from the row, the delegates from the
// rows below. Results are stored per school so they appear where the button was clicked.
const generateHashesForSchool = async (school) => {
  generatingForSchool.value = school.id
  try {
    const hashes = await requestHashes(school.name)
    if (hashes === null) return
    delegateHashesBySchool.value = { ...delegateHashesBySchool.value, [school.id]: hashes }
    toastStore.showToast(`${hashes.length} hash(es) issued for ${school.name}.`, 'success')
  } catch (error) {
    // Errors automatically pop up via global toast interceptor
  } finally {
    generatingForSchool.value = null
  }
}

const loadAllHashes = async () => {
  loadingAllHashes.value = true
  try {
    // No schoolName filter: the endpoint returns every delegate hash when it is omitted.
    const response = await apiClient.get('/admin/hashes')
    allHashes.value = response.data.hashes || []
  } catch (error) {
    // Errors automatically pop up via global toast interceptor
  } finally {
    loadingAllHashes.value = false
  }
}

// ---------- Existing Schools: per-school detail, editing, deletion ----------
const selectedSchoolId = ref(null)
const schoolDetail = ref(null)
const schoolDraft = ref(null)
const delegateDrafts = ref([])
const savingSchool = ref(false)
const savingDelegateId = ref(null)
const reissuingId = ref(null)
const deletingSchool = ref(false)

const applySchoolDetail = (detail) => {
  schoolDetail.value = detail
  schoolDraft.value = { ...detail.school }
  delegateDrafts.value = (detail.delegates || []).map((row) => ({ ...row }))
}

const loadSchoolDetail = async () => {
  if (selectedSchoolId.value === null) {
    schoolDetail.value = null
    schoolDraft.value = null
    delegateDrafts.value = []
    return
  }
  try {
    const response = await apiClient.get(`/admin/schools/${selectedSchoolId.value}`)
    applySchoolDetail(response.data)
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  }
}

const schoolDirty = computed(() => {
  if (!schoolDetail.value || !schoolDraft.value) return false
  return Object.keys(schoolDraft.value).some(
    (key) =>
      String(schoolDraft.value[key] ?? '') !== String(schoolDetail.value.school[key] ?? '')
  )
})

const delegateDirty = (row) => {
  const original = schoolDetail.value?.delegates.find((d) => d.account_id === row.account_id)
  if (!original) return false
  return (
    row.country.trim() !== original.country || row.committee.trim() !== original.committee
  )
}

const saveSchool = async () => {
  if (!schoolDetail.value || !schoolDraft.value) return
  const changes = {}
  for (const key of Object.keys(schoolDraft.value)) {
    if (String(schoolDraft.value[key] ?? '') !== String(schoolDetail.value.school[key] ?? '')) {
      changes[key] = schoolDraft.value[key]
    }
  }

  savingSchool.value = true
  try {
    const response = await apiClient.patch(`/admin/schools/${schoolDetail.value.id}`, changes)
    // A rename rewrites the delegate labels server-side, so refresh from the response -
    // but keep whatever the admin has typed into the editable columns.
    const typed = new Map(delegateDrafts.value.map((row) => [row.account_id, row]))
    applySchoolDetail(response.data)
    delegateDrafts.value = delegateDrafts.value.map((fresh) => {
      const row = typed.get(fresh.account_id)
      return row ? { ...fresh, country: row.country, committee: row.committee } : fresh
    })
    await loadSchools()
    toastStore.showToast('School updated.', 'success')
  } catch (error) {
    // 409 / 400 / 422 all arrive as {"message": ...} and are toasted by the interceptor
  } finally {
    savingSchool.value = false
  }
}

const saveDelegate = async (row) => {
  if (!schoolDetail.value) return false
  const original = schoolDetail.value.delegates.find((d) => d.account_id === row.account_id)
  if (!original) return false

  const changes = {}
  if (row.country.trim() !== original.country) changes.country = row.country.trim()
  if (row.committee.trim() !== original.committee) changes.committee = row.committee.trim()
  if (!Object.keys(changes).length) return true

  savingDelegateId.value = row.account_id
  try {
    const response = await apiClient.patch(
      `/admin/schools/${schoolDetail.value.id}/delegates/${row.account_id}`,
      changes
    )
    Object.assign(row, response.data)
    const index = schoolDetail.value.delegates.findIndex(
      (d) => d.account_id === row.account_id
    )
    if (index !== -1) schoolDetail.value.delegates[index] = { ...response.data }
    toastStore.showToast('Delegate updated.', 'success')
    return true
  } catch (error) {
    return false
  } finally {
    savingDelegateId.value = null
  }
}

const reissueHash = async (row) => {
  // The regenerate endpoint identifies a delegate by committee + country, so pending edits
  // have to be saved first or it would reissue the hash of the old assignment.
  if (delegateDirty(row) && !(await saveDelegate(row))) return
  if (
    !window.confirm(
      `Reissue the hash for ${row.country} (${row.committee})?\n\nThe current hash stops working immediately.`
    )
  ) {
    return
  }

  reissuingId.value = row.account_id
  try {
    const response = await apiClient.post('/admin/hashes/regenerate/delegate', {
      committee: row.committee,
      country: row.country
    })
    row.hash = response.data.hash
    const original = schoolDetail.value.delegates.find((d) => d.account_id === row.account_id)
    if (original) original.hash = response.data.hash
    toastStore.showToast('Hash reissued.', 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    reissuingId.value = null
  }
}

const deleteSchool = async () => {
  const detail = schoolDetail.value
  if (!detail) return

  const delegates = detail.delegates.length
  const papers = detail.delegates.filter((row) => row.has_paper).length
  const warning =
    `Delete "${detail.school.school_name}"?\n\n` +
    `This removes ${delegates} delegate(s) and their hashes` +
    (papers ? `, plus ${papers} stored paper(s)` : '') +
    '.\n\nThis cannot be undone.'
  if (!window.confirm(warning)) return

  deletingSchool.value = true
  try {
    const response = await apiClient.delete(`/admin/schools/${detail.id}`, {
      // The server checks this, so a stray request cannot delete a school by id alone.
      params: { confirm: detail.school.school_name }
    })
    toastStore.showToast(
      `${response.data.school} deleted (${response.data.delegates_deleted} delegate(s)).`,
      'success'
    )
    selectedSchoolId.value = null
    schoolDetail.value = null
    schoolDraft.value = null
    delegateDrafts.value = []
    await loadSchools()
  } catch (error) {
    // toasted by the interceptor
  } finally {
    deletingSchool.value = false
  }
}

// Entry refresh, matching what the old switchTab did: fetch the list only if it is cold,
// and keep the committee suggestions current so the datalist never goes stale.
onActivated(() => {
  if (!schools.value.length) loadSchools()
  if (!committeeNames.value.length) loadCommitteeNames()
})

</script>
