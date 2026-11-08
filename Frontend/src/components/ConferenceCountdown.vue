<template>
  <div v-if="parts" class="countdown" :class="{ 'is-live': parts.live }">
    <span v-if="parts.live" class="countdown-live">Conference is Live!</span>
    <template v-else>
      <span class="countdown-label">{{ label }}</span>
      <span class="countdown-value">
        <strong>{{ parts.days }}</strong><span class="unit">d</span>
        <strong>{{ pad(parts.hours) }}</strong><span class="unit">h</span>
        <strong>{{ pad(parts.minutes) }}</strong><span class="unit">m</span>
        <strong>{{ pad(parts.seconds) }}</strong><span class="unit">s</span>
      </span>
    </template>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import apiClient from '@/api/client'
import { pad, remainingParts } from '@/utils/countdown'

// The conference start comes from the pinned "Conference Start" timeline event, read
// through the public /conference route. Nothing is invented client-side: if the route has
// no date, the timer simply does not render.
const label = ref('Starts in')
const parts = ref(null)

let target = null
let timer = null

const tick = () => {
  parts.value = remainingParts(target)
  // Stop ticking once it has gone live; there is nothing left to count.
  if (parts.value?.live && timer) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(async () => {
  try {
    const response = await apiClient.get('/conference')
    target = response.data?.starts_at || null
    if (response.data?.label) label.value = `${response.data.label} in`
  } catch (error) {
    target = null // the header should degrade to nothing, not to an error
  }

  if (!target) return
  tick()
  if (parts.value && !parts.value.live) timer = setInterval(tick, 1000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.countdown {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.92rem;
  color: #00007ecc;
  white-space: nowrap;
}

.countdown-label {
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 0.75rem;
  opacity: 0.7;
}

.countdown-value strong {
  font-variant-numeric: tabular-nums;
  font-size: 1rem;
}

.countdown-value .unit {
  margin: 0 6px 0 2px;
  font-size: 0.82rem;
  opacity: 0.7;
}

.countdown-live {
  font-weight: 700;
  color: #1a7f37;
  letter-spacing: 0.02em;
}

/* On narrow screens the label is the first thing to go; the numbers stay. */
@media (max-width: 760px) {
  .countdown-label {
    display: none;
  }
}
</style>
