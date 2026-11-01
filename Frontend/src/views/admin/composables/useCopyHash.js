import { useToastStore } from '@/stores/toast'

/**
 * Copy a hash to the clipboard and say so.
 *
 * Shared by the Schools and Committees tabs, which both list hashes with a Copy button.
 * The toast wording is the dashboard's, unchanged.
 */
export function useCopyHash() {
  const toastStore = useToastStore()

  const copyHash = async (hash) => {
    try {
      await navigator.clipboard.writeText(hash)
      toastStore.showToast('Hash copied to clipboard.', 'success')
    } catch (error) {
      toastStore.showToast('Could not copy the hash.', 'error')
    }
  }

  return { copyHash }
}
