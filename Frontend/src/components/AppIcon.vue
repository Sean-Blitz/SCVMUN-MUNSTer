<template>
  <svg
    class="app-icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path v-for="(d, index) in paths" :key="index" :d="d" />
  </svg>
</template>

<script setup>
import { computed } from 'vue'

// One family of drawn marks, all inheriting currentColor, so an icon matches the ink of
// the label beside it. Names cover the actions this app actually has; there is no
// fallback glyph for a misspelt name on purpose - a blank space shows the typo.
const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 16 }
})

const PATHS = {
  refresh: [
    'M21 12a9 9 0 1 1-2.64-6.36',
    'M21 3v6h-6'
  ],
  file: [
    'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z',
    'M14 3v5h5',
    'M9 13h6',
    'M9 17h6'
  ],
  tools: [
    'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z'
  ],
  chart: [
    'M4 6.5c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z',
    'M4 6.5v11c0 1.7 3.6 3 8 3s8-1.3 8-3v-11',
    'M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3'
  ],
  check: [
    'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z',
    'M8 12.3l2.6 2.6L16 9.4'
  ],
  warning: [
    'M12 4 3.5 19h17z',
    'M12 10v4',
    'M12 16.6v.2'
  ],
  up: ['M6 14.5 12 8.5l6 6'],
  down: ['M6 9.5 12 15.5l6-6'],
  close: ['M6 6l12 12', 'M18 6 6 18']
}

const paths = computed(() => PATHS[props.name] || [])
</script>

<style scoped>
.app-icon {
  display: inline-block;
  flex: none;
  vertical-align: -0.16em;
}
</style>
