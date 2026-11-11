<template>
<div class="section-card">
  <h2>Conference Action Checklist</h2>
  <p class="section-desc">
    The checklist lines shown on <strong>every</strong> advisor's dashboard — the labels
    are shared, the ticks are per school (on the right). Add, rename or remove lines; Save
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
</template>

<script setup>
import AppIcon from '@/components/AppIcon.vue'
import { onActivated } from 'vue'
import { useChecklistAdmin } from '../../composables/useChecklistAdmin'

// The shared labels half. Saving them re-reads the progress card's ticks, which is why the
// two cards share one composable instead of passing props between them.
const {
  checklistItems,
  loadingChecklist,
  savingChecklist,
  checklistDirty,
  maxChecklistItems,
  loadChecklist,
  addChecklistItem,
  removeChecklistItem,
  saveChecklist
} = useChecklistAdmin()

// Refreshed on entry, but never over an unsaved draft - the same rule the old tab had.
onActivated(() => {
  if (!checklistDirty.value) loadChecklist()
})
</script>
