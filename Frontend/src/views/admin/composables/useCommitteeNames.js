import { ref } from 'vue'
import apiClient from '@/api/client'

/**
 * The committee-name list, shared.
 *
 * Schools Management needs it for the `<datalist>` behind every committee field (a delegate
 * can only be minted into a committee that exists) and Committees renders it as a dropdown.
 * One module-level ref keeps them in step after a committee is created.
 */
const committeeNames = ref([])

export function useCommitteeNames() {
  const loadCommitteeNames = async () => {
    try {
      const response = await apiClient.get('/admin/committees')
      committeeNames.value = response.data || []
    } catch (error) {
      // toasted by the interceptor
    }
  }

  return { committeeNames, loadCommitteeNames }
}
