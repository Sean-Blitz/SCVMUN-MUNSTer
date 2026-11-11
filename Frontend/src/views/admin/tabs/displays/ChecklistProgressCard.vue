<template>
<div class="section-card">
  <h2>Checklist Progress</h2>
  <p class="section-desc">
    This is shown on the advisor's dashboard, corresponding to the action checklist
    (on the left). Which lines a school has ticked. Pick a school and tick its boxes for
    progress.
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
import { onActivated } from 'vue'
import { useChecklistAdmin } from '../../composables/useChecklistAdmin'
import { useSchools } from '../../composables/useSchools'

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
  saveProgress
} = useChecklistAdmin()

const { schools, loadSchools } = useSchools()

onActivated(() => {
  if (!schools.value.length) loadSchools()
})
</script>
