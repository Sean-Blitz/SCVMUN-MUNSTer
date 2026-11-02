<template>
  <button
    ref="hostEl"
    :type="type"
    :disabled="disabled"
    class="soap-bubble-surface soap-bubble-button"
    data-soap-bubble
    :data-soap-bubble-ready="ready ? '' : undefined"
  >
    <!-- The film is drawn here; the label stays real DOM text on top. -->
    <canvas ref="canvasEl" class="soap-bubble-surface-canvas" aria-hidden="true"></canvas>
    <slot />
  </button>
</template>

<script setup>
import { ref, watch } from 'vue'
import './soap-bubble.css'
import { useSoapBubble } from './useSoapBubble'

const props = defineProps({
  type: { type: String, default: 'button' },
  disabled: { type: Boolean, default: false },
  /** Material overrides: thin film, lighting and reflection settings. */
  material: { type: Object, default: () => ({}) },
  /** Element whose pixels show through and mirror in the rim. */
  backdrop: { type: [Object, null], default: null }
})

const hostEl = ref(null)
const canvasEl = ref(null)

// Root element is the <button>, so class, listeners and aria all fall through
// from the parent unchanged — same contract as the React component.
const { ready, engine } = useSoapBubble({
  host: hostEl,
  canvas: canvasEl,
  material: props.material,
  backdrop: props.backdrop,
  interactive: true
})

// The backdrop is usually the parent's page element, whose template ref is only
// assigned after this child mounts: follow it, rather than capturing it once.
watch(
  () => props.backdrop,
  (element) => engine.value?.setBackdrop(element ?? null)
)
</script>
