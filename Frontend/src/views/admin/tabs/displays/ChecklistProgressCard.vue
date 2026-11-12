<template>
<div class="section-card">
  <h2>Checklist Progress</h2>
  <p class="section-desc">
    This is what the advisors' dashboards report, against the action checklist on the left.
    Every school's total is listed below; pick one to tick its individual lines. Advisors
    tick their own, so this is for checking and correcting.
  </p>

  <!-- EVERY SCHOOL: SELECT THEM, THEN TICK FOR ALL OF THEM AT ONCE -->
  <div v-if="schools.length" class="overview-block">
    <div class="overview-head">
      <h3>All schools</h3>
      <label class="overview-select-all">
        <input
          type="checkbox"
          :checked="allSelected"
          :indeterminate="selectedCount > 0 && !allSelected"
          @change="toggleAll"
        />
        Select all schools
      </label>
    </div>

    <p v-if="loadingAllProgress" class="section-desc">Loading every school's progress…</p>
    <div v-else class="overview-list">
      <div
        v-for="school in schools"
        :key="school.id"
        :class="['overview-row', { 'is-selected': progressSchoolId === school.id }]"
      >
        <input
          type="checkbox"
          :checked="isSelected(school.id)"
          :aria-label="`Include ${school.name}`"
          @change="toggleSchool(school.id)"
        />
        <button type="button" class="overview-open" :title="`Edit ${school.name} below`" @click="selectSchool(school)">
          {{ school.name }}
        </button>
        <span class="overview-bar">
          <span class="overview-fill" :style="{ width: progressPercent(school.id) + '%' }"></span>
        </span>
        <span class="overview-count">{{ progressCount(school.id) }}</span>
      </div>
    </div>

    <!-- BULK EDIT: one checkbox per line, applied to every selected school -->
    <div class="bulk-block">
      <p class="bulk-title">
        Tick for the selected schools
        <span class="bulk-count">{{ selectedCount }} of {{ schools.length }} selected</span>
      </p>

      <p v-if="!selectedCount" class="capacity-note">
        Select at least one school above — "Select all schools" does it in one click.
      </p>
      <p v-else-if="!savedLines.length" class="capacity-note">
        No checklist lines yet — add some on the left and save first.
      </p>
      <div v-else class="bulk-lines">
        <label v-for="item in savedLines" :key="item.id" class="bulk-line">
          <input
            type="checkbox"
            :checked="lineAllDone(item)"
            :disabled="bulkSaving"
            @change="applyLine(item, $event.target.checked)"
          />
          <span class="bulk-label">{{ item.label }}</span>
          <span class="bulk-meta">{{ lineDoneCount(item) }}/{{ selectedCount }}</span>
        </label>
      </div>
    </div>

    <p class="capacity-note">Click a school's name to tick its individual lines below.</p>
  </div>

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
        No checklist lines to tick yet — add some on the left and save first.
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
import { computed, onActivated, ref } from 'vue'
import { useToastStore } from '@/stores/toast'
import { useChecklistAdmin } from '../../composables/useChecklistAdmin'
import { useSchools } from '../../composables/useSchools'

const toastStore = useToastStore()

// The per-school half. The school list is the shared one (useSchools), because Schools
// Management creates those rows and the picker must see a new school without a reload.
const {
  progressSchoolId,
  progressItems,
  loadingProgress,
  savingProgress,
  progressDirty,
  progressDone,
  onProgressSchoolChange,
  saveProgress,
  allProgress,
  loadingAllProgress,
  loadAllProgress,
  bulkSaving,
  applyToSchools,
  checklistItems
} = useChecklistAdmin()

const { schools, loadSchools } = useSchools()

// ---------- Selection + bulk ticking ----------
// The selection decides which schools a line checkbox applies to. It starts empty so nothing
// is changed by accident; "Select all schools" fills it in one click.
const selectedSchoolIds = ref([])
const selectedCount = computed(() => selectedSchoolIds.value.length)
const allSelected = computed(
  () => schools.value.length > 0 && selectedCount.value === schools.value.length
)

const isSelected = (schoolId) => selectedSchoolIds.value.includes(schoolId)

const toggleSchool = (schoolId) => {
  selectedSchoolIds.value = isSelected(schoolId)
    ? selectedSchoolIds.value.filter((id) => id !== schoolId)
    : [...selectedSchoolIds.value, schoolId]
}

const toggleAll = (event) => {
  selectedSchoolIds.value = event.target.checked ? schools.value.map((school) => school.id) : []
}

// Only saved lines can be written by id; a line the admin has just added on the left is
// still a draft with no id until the checklist is saved.
const savedLines = computed(() => checklistItems.value.filter((item) => item.id !== null))

// How many of the selected schools have this line ticked.
const lineDoneCount = (item) =>
  selectedSchoolIds.value.filter((schoolId) =>
    (allProgress.value[schoolId]?.completedIds || []).includes(item.id)
  ).length

const lineAllDone = (item) => selectedCount.value > 0 && lineDoneCount(item) === selectedCount.value

// Ticking a line sets it for every selected school at once; the checkbox clears it likewise.
const applyLine = async (item, completed) => {
  if (!selectedCount.value) return
  try {
    const result = await applyToSchools(selectedSchoolIds.value, [
      { id: item.id, completed }
    ])
    toastStore.showToast(
      `${completed ? 'Ticked' : 'Cleared'} "${item.label}" for ${result.schools} school(s).`,
      'success'
    )
  } catch (error) {
    // toasted by the interceptor
  }
}

// A row in the summary selects that school in the editor below, going through the same
// unsaved-changes check the picker uses.
const selectSchool = (school) => {
  if (progressSchoolId.value === school.id) return
  progressSchoolId.value = school.id
  onProgressSchoolChange()
}

const progressPercent = (schoolId) => {
  const entry = allProgress.value[schoolId]
  if (!entry || !entry.total) return 0
  return Math.round((entry.done / entry.total) * 100)
}

const progressCount = (schoolId) => {
  const entry = allProgress.value[schoolId]
  return entry ? `${entry.done}/${entry.total}` : '—'
}

onActivated(async () => {
  // Show the loading line straight away: the school list is usually warm, so without this
  // the summary would flash "—" for every row while the fan-out is in flight.
  loadingAllProgress.value = true
  if (!schools.value.length) await loadSchools()
  await loadAllProgress()
})
</script>
