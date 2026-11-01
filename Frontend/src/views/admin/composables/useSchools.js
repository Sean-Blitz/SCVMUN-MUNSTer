import { ref } from 'vue'
import apiClient from '@/api/client'

/**
 * The school list, shared.
 *
 * Two tabs need it: Schools Management renders it (dropdown + advisor hashes) and Delegate
 * Content uses it for the checklist-progress picker. One module-level ref means a school
 * created in one tab is already there in the other.
 *
 * `loadSchools()` always refetches, because callers use it after a write; tabs that only
 * want a warm list guard with `if (!schools.value.length)`.
 */
const schools = ref([])

export function useSchools() {
  const loadSchools = async () => {
    try {
      const response = await apiClient.get('/admin/schools')
      schools.value = response.data.schools || []
    } catch (error) {
      // Backend errors pop up via the global toast interceptor
    }
  }

  return { schools, loadSchools }
}
