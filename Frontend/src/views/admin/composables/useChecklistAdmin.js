import { computed, ref } from 'vue'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'

/**
 * The conference-wide action checklist and its per-school ticks, shared by the two cards that
 * own them.
 *
 * They are one composable because they are one feature seen from two angles: the left card
 * edits the shared labels, the right card ticks them off for one school. Saving the labels
 * changes the ids the ticks point at, so the progress card has to be re-read afterwards - it
 * is the same `loadProgress` either way, which is why this state is module-level rather than
 * split across props.
 */

const checklistItems = ref([])
const loadingChecklist = ref(false)
const savingChecklist = ref(false)
const checklistDirty = ref(false)
const maxChecklistItems = 20 // mirrors MAX_CHECKLIST_ITEMS in admin.py

const progressSchoolId = ref(null)
// The school the tick draft belongs to, so a cancelled switch can put the picker back.
const savedProgressSchoolId = ref(null)
const progressItems = ref([])
const loadingProgress = ref(false)
const savingProgress = ref(false)
const progressDirty = ref(false)

const progressDone = computed(
  () => progressItems.value.filter((item) => item.completed).length
)

// ---------- Shared labels ----------
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

// Declared before saveChecklist uses it; both are function declarations, so hoisting makes
// the call inside saveChecklist resolve to this one.
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

const saveChecklist = async () => {
  const toastStore = useToastStore()
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

// ---------- Per-school ticks ----------
// Switching schools throws the tick draft away, so ask first and put the picker back.
const onProgressSchoolChange = async () => {
  if (progressDirty.value && !window.confirm('Discard the unsaved progress changes?')) {
    progressSchoolId.value = savedProgressSchoolId.value
    return
  }
  await loadProgress()
}

const saveProgress = async () => {
  const toastStore = useToastStore()
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

export function useChecklistAdmin() {
  return {
    // shared labels
    checklistItems,
    loadingChecklist,
    savingChecklist,
    checklistDirty,
    maxChecklistItems,
    loadChecklist,
    addChecklistItem,
    removeChecklistItem,
    saveChecklist,
    // per-school progress
    progressSchoolId,
    progressItems,
    loadingProgress,
    savingProgress,
    progressDirty,
    progressDone,
    loadProgress,
    onProgressSchoolChange,
    saveProgress
  }
}
