<template>
  <div class="delegate-page">
    <!-- PLATFORM: the page's own header, replacing the shell's navbar on this dashboard. -->
    <header
      ref="barEl"
      class="platform-bar soap-bubble-surface"
      :data-soap-bubble-ready="barReady ? '' : undefined"
    >
      <!-- The film: the same liquid glass the login buttons wear, drawn behind the content
           so the rim can wobble past the header's box. -->
      <canvas ref="barCanvasEl" class="soap-bubble-surface-canvas" aria-hidden="true"></canvas>

      <div class="bar-left">
        <ConferenceCountdown class="bar-countdown" />
      </div>

      <h1 class="bar-title">
        <span
          v-for="(glyph, index) in titleGlyphs"
          :key="index"
          class="glyph"
          :style="{ animationDelay: `${0.18 + index * 0.018}s` }"
        >{{ glyph }}</span>
      </h1>

      <div class="bar-right">
        <span class="user-name">{{ currentUser.name }}</span>
        <button class="btn-logout" @click="handleLogout">Logout</button>
      </div>
    </header>

    <!-- DASHBOARD: the whole brief on one screen - no scrolling, no scroll-driven motion -->
    <main class="dashboard">
      <!-- ANNOUNCEMENT BAR (the backend sends at most 3: 2 general + 1 for this committee) -->
      <div v-if="dashboardData.announcements.length" class="announcement-bar">
        <span class="announcement-label">
          {{ dashboardData.announcements.length > 1 ? 'Announcements' : 'Announcement' }}
        </span>
        <div class="announcement-lines">
          <span
            v-for="(announcement, index) in dashboardData.announcements"
            :key="index"
            class="announcement-text"
          >
            {{ announcement }}
          </span>
        </div>
      </div>

      <!-- THREE COLUMNS: identity + links, the paper, and the chair's verdict -->
      <div class="board">
        <div class="column">
          <!-- DELEGATE INFO PANEL -->
          <section class="panel panel-delegate">
            <h2 class="panel-title">Delegate Information</h2>
            <div class="info-content">
              <div class="info-row">
                <span class="info-label">Committee</span>
                <span class="info-value">{{ dashboardData.delegate.committee || 'Unassigned' }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">Country Assignment</span>
                <span class="info-value">{{ dashboardData.delegate.country || 'Unassigned' }}</span>
              </div>
            </div>
          </section>

          <!-- CONFERENCE / GENERAL INFO PANEL -->
          <section class="panel panel-links">
            <h2 class="panel-title">Conference &amp; General Info</h2>
            <div class="links-container">
              <div
                v-for="(link, index) in formattedLinks"
                :key="index"
                class="link-box"
              >
                <a
                  v-if="link.url && link.text"
                  :href="link.url"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <span class="link-name">{{ link.text }}</span>
                  <span class="link-url">{{ link.url }}</span>
                </a>
              </div>
            </div>
          </section>
        </div>

        <!-- SUBMISSION PANEL -->
        <section class="panel panel-paper">
          <h2 class="panel-title">Position Paper Submission</h2>

          <!-- INSTRUCTIONS LIST -->
          <div v-if="positionPaper.instructions.length" class="instructions-block">
            <ol class="instructions-list">
              <li
                v-for="(instruction, index) in positionPaper.instructions"
                :key="index"
              >
                {{ instruction }}
              </li>
            </ol>
          </div>

          <!-- STATUS DISPLAY -->
          <div class="status-block">
            <span class="status-label">Current Status</span>
            <span :class="['status-badge', statusClass]">
              {{ positionPaper.status.toUpperCase() }}
            </span>
          </div>

          <!-- OWN PAPER DOWNLOAD, once something has been submitted -->
          <div v-if="positionPaper.status !== 'unsubmitted'" class="paper-download-block">
            <button class="btn-download-paper" :disabled="downloadingPaper" @click="downloadMyPaper">
              <span class="btn-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 4v10" />
                  <path d="m8 10 4 4 4-4" />
                  <path d="M5 19h14" />
                </svg>
              </span>
              <span>{{ downloadingPaper ? 'Preparing…' : 'Download my position paper' }}</span>
            </button>
            <span class="download-hint">The copy you submitted, as a PDF.</span>
          </div>

          <!-- FILE UPLOAD BOX -->
          <form @submit.prevent="submitPaper" class="upload-box">
            <label for="pdf-upload" class="upload-label">Select PDF Document</label>
            <input
              id="pdf-upload"
              type="file"
              accept="application/pdf"
              @change="handleFileSelect"
              class="file-input"
            />
            <button
              type="submit"
              class="btn-submit"
              :disabled="!selectedFile"
            >
              Upload Position Paper
            </button>
          </form>
        </section>

        <!-- GRADE & FEEDBACK PANEL -->
        <section class="panel panel-grade">
          <h2 class="panel-title">Grade &amp; Chair Feedback</h2>

          <!-- AWAITING GRADING -->
          <div v-if="!isGraded" class="grade-empty">
            <span class="grade-empty-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7.5V12l3 1.8" />
              </svg>
            </span>
            <p v-if="positionPaper.status === 'submitted'">
              Your position paper has been submitted and is awaiting grading by your chair.
            </p>
            <p v-else>
              Upload your position paper to receive a grade and written feedback from your chair.
            </p>
          </div>

          <!-- GRADED -->
          <template v-else>
            <div class="grade-summary">
              <div class="grade-total">
                <span class="grade-total-label">Final Score</span>
                <strong class="grade-total-value">{{ scoreDisplay }}</strong>
              </div>
              <span :class="['status-badge', statusClass]">
                {{ positionPaper.status.toUpperCase() }}
              </span>
            </div>

            <div v-if="criteria.length" class="rubric-breakdown">
              <h3 class="subsection-title">Rubric Breakdown</h3>
              <div
                v-for="criterion in criteria"
                :key="criterion.id"
                class="criterion-row"
              >
                <div class="criterion-head">
                  <span class="criterion-label">{{ criterion.label }}</span>
                  <span class="criterion-score">{{ criterion.score }} / {{ criterion.maxScore }}</span>
                </div>
                <div class="criterion-bar-bg">
                  <div
                    class="criterion-bar-fill"
                    :class="{ low: criterionPercent(criterion) < 50 }"
                    :style="{ width: criterionPercent(criterion) + '%' }"
                  ></div>
                </div>
              </div>
            </div>
            <p v-else class="grade-muted">
              No per-criterion breakdown was recorded for this paper.
            </p>

            <div class="feedback-block">
              <h3 class="subsection-title">Chair Comments</h3>
              <p class="feedback-text">{{ feedback || 'No comments were provided.' }}</p>
            </div>
          </template>
        </section>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { useLogout } from '@/utils/useLogout'
import ConferenceCountdown from '@/components/ConferenceCountdown.vue'
import { useSoapBubble } from '@/components/soap-bubble/useSoapBubble'
import '@/components/soap-bubble/soap-bubble.css'

const toastStore = useToastStore()
const authStore = useAuthStore()
const { handleLogout } = useLogout()

// The platform shows who is signed in, exactly as the shell's navbar did.
const currentUser = computed(() => authStore.user || { name: 'Guest', role: 'none' })

// ---------- Platform glass (the soap-bubble film) ----------
// The header is a real bubble surface, not a painted panel: the material draws its film on
// the canvas below and the pointer handlers at the bottom of the script nudge it, so the
// bar jiggles under the cursor exactly as the login buttons do.
const barEl = ref(null)
const barCanvasEl = ref(null)

// The login page's approved light-glass preset, with a milky body so the countdown and the
// title stay readable over the bright dashboard, and a livelier wobble than a button has
// because the jiggle has a 880px bar to travel through.
const barMaterial = {
  glass: 0.95,
  iridescence: 0.5,
  filmScale: 4.85,
  oilOpacity: 1,
  oilCoverage: 0.73,
  oilEdge: 18,
  oilEdgeFade: 2.33,
  clearCenter: 0.57,
  thickness: 480,
  drainage: 0.35,
  swirl: 0.5,
  reflectivity: 1.3,
  refraction: 0.15,
  dispersion: 1,
  bevel: 14,
  environment: 'soft',
  windowLength: 1.3,
  windowMargin: 0.85,
  windowBend: 0.75,
  windowSize: 0.75,
  windowWidth: 0.8,
  windowGradient: 0.96,
  windowHead: 0.7,
  windowTail: 0.6,
  glintSize: 1.65,
  glintIntensity: 0,
  glintDistance: -0.45,
  glintHeight: 0.65,
  windowIntensity: 0.85,
  windowTwin: false,
  tint: '#ffffff',
  // The film has no backdrop blur of its own, so the body carries enough milk to keep the
  // header's own text clear of whatever panel sits underneath it.
  opacity: 0.62,
  bottomShadeColor: '#ffffff',
  wobble: 1.7
}

// Pointer handling is bound here rather than by the composable: a bar is tens of times wider
// than it is tall, and the composable normalises by the shorter side, which would send the
// film's lean far past anything the shader expects.
const { ready: barReady, engine: barEngine } = useSoapBubble({
  host: barEl,
  canvas: barCanvasEl,
  material: barMaterial,
  interactive: false
})

// Position on the bar in -1..1 on both axes, measured against the bar itself.
const barPoint = (event) => {
  const el = barEl.value
  if (!el) return [0, 0]
  const rect = el.getBoundingClientRect()
  const halfWidth = rect.width / 2 || 1
  const halfHeight = rect.height / 2 || 1
  return [
    (event.clientX - rect.left - halfWidth) / halfWidth,
    -(event.clientY - rect.top - halfHeight) / halfHeight
  ]
}

// Crossing the edge gives the film a jolt, so hovering reads as a nudge, not a glow.
const onBarEnter = (event) => {
  const [x, y] = barPoint(event)
  barEngine.value?.pointer(x, y, true)
  barEngine.value?.rebound()
}

const onBarMove = (event) => {
  const [x, y] = barPoint(event)
  barEngine.value?.pointer(x, y, true)
}

const onBarLeave = (event) => {
  const [x, y] = barPoint(event)
  barEngine.value?.pointer(x, y, false)
  barEngine.value?.press(false)
}

const onBarDown = () => barEngine.value?.press(true)
const onBarUp = () => barEngine.value?.press(false)

onMounted(() => {
  const el = barEl.value
  if (!el) return
  el.addEventListener('pointerenter', onBarEnter)
  el.addEventListener('pointermove', onBarMove)
  el.addEventListener('pointerleave', onBarLeave)
  el.addEventListener('pointerdown', onBarDown)
  el.addEventListener('pointerup', onBarUp)
})

onBeforeUnmount(() => {
  const el = barEl.value
  if (!el) return
  el.removeEventListener('pointerenter', onBarEnter)
  el.removeEventListener('pointermove', onBarMove)
  el.removeEventListener('pointerleave', onBarLeave)
  el.removeEventListener('pointerdown', onBarDown)
  el.removeEventListener('pointerup', onBarUp)
})

// ---------- Wordmark (presentation only) ----------
// The title assembles itself a letter at a time on load. Each glyph carries its own delay,
// so no timer runs in the script once the page has mounted.
const TITLE = 'SCVMUN Munster'

// Spacing glyphs keep their width as flex items, so words keep their gaps.
const titleGlyphs = TITLE.split('').map((char) => (char === ' ' ? '\u00A0' : char))

// Local state for dashboard data
const dashboardData = ref({
  announcements: [],
  delegate: {
    committee: '',
    country: ''
  },
  conferenceLinks: [],
  positionPaper: {
    status: 'unsubmitted', // 'unsubmitted', 'submitted', 'graded'
    score: '',
    feedback: '',
    instructions: [],
    criteria: []
  }
})

const selectedFile = ref(null)
const downloadingPaper = ref(false)

// Shorthand for the position paper panel state
const positionPaper = computed(() => dashboardData.value.positionPaper)

// Pad or trim links array to strictly 5 slot boxes
const formattedLinks = computed(() => {
  const links = [...(dashboardData.value.conferenceLinks || [])]
  while (links.length < 5) {
    links.push({ text: '', url: '' })
  }
  return links.slice(0, 5)
})

// Dynamic class for status indicators
const statusClass = computed(() => {
  switch (dashboardData.value.positionPaper.status) {
    case 'submitted':
      return 'status-submitted'
    case 'graded':
      return 'status-graded'
    case 'unsubmitted':
    default:
      return 'status-unsubmitted'
  }
})

/* --- Chair grade & feedback --- */

// The grade panel only shows results once a chair has graded the paper
const isGraded = computed(() => positionPaper.value.status === 'graded')

// Per-criterion marks, already joined with their labels and maxima by the backend
const criteria = computed(() => positionPaper.value.criteria || [])

const scoreDisplay = computed(() => {
  const raw = positionPaper.value.score
  return raw === '' || raw === null || raw === undefined ? '—' : raw
})
const feedback = computed(() => positionPaper.value.feedback || '')

// Percentage of the maximum for a single rubric criterion (guards against maxScore 0)
const criterionPercent = (criterion) => {
  const max = Number(criterion.maxScore)
  if (!max) return 0
  return Math.min(100, Number(((Number(criterion.score) / max) * 100).toFixed(1)))
}

// File selection handler
const handleFileSelect = (event) => {
  const file = event.target.files[0]
  if (file && file.type === 'application/pdf') {
    selectedFile.value = file
  } else {
    selectedFile.value = null
  }
}

// Upload submission function
const submitPaper = async () => {
  if (!selectedFile.value) return

  const formData = new FormData()
  formData.append('paper', selectedFile.value)

  try {
    // No explicit Content-Type: the browser has to add the multipart boundary, and
    // setting the header by hand would send "multipart/form-data" without one.
    await apiClient.post('/delegate/upload-paper', formData)

    // Reflect the new status locally so the panel updates immediately
    dashboardData.value.positionPaper.status = 'submitted'
    selectedFile.value = null
    toastStore.showToast('Paper submitted successfully!', 'success')
  } catch (error) {
    // Backend errors are surfaced globally by the client.js toast interceptor
  }
}

// Download the delegate's own submitted paper. Fetched as a blob because a plain link
// would not carry the Authorization header.
const downloadMyPaper = async () => {
  downloadingPaper.value = true
  try {
    const response = await apiClient.get('/delegate/my-paper', { responseType: 'blob' })

    const blob = new Blob([response.data], { type: 'application/pdf' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute(
      'download',
      `${dashboardData.value.delegate.country || 'My'}_Position_Paper.pdf`
    )
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (error) {
    // A 404 (nothing submitted, or the stored file is gone) surfaces via the toast interceptor
  } finally {
    downloadingPaper.value = false
  }
}

// Fetch dashboard data from backend on mount
onMounted(async () => {
  try {
    const response = await apiClient.get('/delegate/my-assignment')
    const data = response.data || {}

    // Merge defensively so a partial payload still renders (and never throws in template)
    dashboardData.value = {
      announcements: data.announcements || [],
      delegate: {
        committee: data.delegate?.committee || '',
        country: data.delegate?.country || ''
      },
      conferenceLinks: data.conferenceLinks || [],
      positionPaper: {
        status: data.positionPaper?.status || 'unsubmitted',
        score: data.positionPaper?.score ?? '',
        feedback: data.positionPaper?.feedback || '',
        instructions: data.positionPaper?.instructions || [],
        criteria: data.positionPaper?.criteria || []
      }
    }
  } catch (error) {
    // Backend errors are surfaced globally by the client.js toast interceptor
  }
})
</script>

<style scoped>
/* ============================================================ PAGE ====== */
/* One screen, no scroll: the header, the announcements and the three cards are laid out
   to fill the viewport, with every type size tied to the page's own font size so the
   whole composition tightens together on shorter screens instead of overflowing. */
.delegate-page {
  --shell-pad: 20px; /* matches AppLayout's main padding, which the page cancels out */
  --ink: #03045e;
  --ink-2: #232d5c;
  --muted: #63708c;
  --line: rgba(3, 4, 94, 0.09);
  --accent: #009ddb;
  --gold: #e8c604;
  --green: #16a34a;
  --gap: clamp(10px, 1.5vh, 16px);
  --radius: 18px;
  --ease: cubic-bezier(0.22, 1, 0.36, 1);
  --font:
    'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto,
    'Helvetica Neue', Arial, sans-serif;

  position: relative;
  isolation: isolate;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  min-height: calc(100svh - 2 * var(--shell-pad));
  margin: calc(-1 * var(--shell-pad));
  padding: clamp(14px, 2.1vh, 24px) clamp(16px, 2.4vw, 34px) clamp(12px, 1.8vh, 20px);
  color: var(--muted);
  font-family: var(--font);
  font-size: clamp(0.85rem, 1.6vh, 1rem);
  line-height: 1.5;
  letter-spacing: 0.005em;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background:
    radial-gradient(120% 90% at 8% -10%, rgba(0, 157, 219, 0.1), transparent 55%),
    radial-gradient(90% 80% at 100% 0%, rgba(232, 198, 4, 0.09), transparent 60%),
    linear-gradient(180deg, #fbfdff 0%, #f4f8fc 55%, #eef4fa 100%);
}

/* AMBIENT LIGHT: two very soft bodies of colour that drift, so the flat page breathes.
   They sit behind everything and take no pointer. */
.delegate-page::before,
.delegate-page::after {
  content: '';
  position: absolute;
  z-index: -1;
  width: min(46vw, 520px);
  aspect-ratio: 1;
  border-radius: 50%;
  filter: blur(70px);
  pointer-events: none;
}

.delegate-page::before {
  top: -18%;
  left: -10%;
  background: radial-gradient(circle, rgba(0, 157, 219, 0.28), transparent 68%);
  animation: drift-a 24s ease-in-out infinite alternate;
}

.delegate-page::after {
  right: -12%;
  bottom: -24%;
  background: radial-gradient(circle, rgba(232, 198, 4, 0.24), transparent 68%);
  animation: drift-b 28s ease-in-out infinite alternate;
}

@keyframes drift-a {
  to { transform: translate3d(60px, 36px, 0) scale(1.12); }
}

@keyframes drift-b {
  to { transform: translate3d(-54px, -30px, 0) scale(1.08); }
}

/* ========================================================== PLATFORM ==== */
/* A rounded capsule that owns the top of the page: countdown on the left, the wordmark in
   the centre, session details on the right. */
.platform-bar {
  position: relative;
  z-index: 2;
  flex: none;
  width: 100%;
  max-width: 1240px;
  height: clamp(48px, 6.4vh, 60px);
  margin: 0 auto;
  padding: 0 18px;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 16px;
  /* LAYOUT ONLY: the glass is the soap-bubble film on the canvas below, so the header itself
     stays transparent. Anything painted here would sit still while the film wobbles. */
  background: transparent;
  border: 0;
  border-radius: 999px;
  /* The film moves and a CSS shadow cannot follow it, so this one stays wide and soft. */
  --soap-bubble-shadow: 0 18px 34px -26px rgba(3, 4, 94, 0.55);
  box-shadow: var(--soap-bubble-shadow);
  animation: bar-in 0.85s var(--ease) both;
}

@keyframes bar-in {
  from {
    opacity: 0;
    transform: translate3d(0, -14px, 0);
  }
}

/* FALLBACK: the CSS pane that stands in until the film's first frame - and for good when
   WebGL is unavailable. It never shows while the canvas is drawing. */
.platform-bar:not([data-soap-bubble-ready]) {
  background-color: rgba(255, 255, 255, 0.46);
  background-image:
    /* The body of the glass: brighter where it faces the light, cooler along the underside. */
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.5) 0%,
      rgba(255, 255, 255, 0.14) 38%,
      rgba(255, 255, 255, 0.06) 66%,
      rgba(214, 236, 255, 0.32) 100%
    ),
    /* A long diagonal sheen, the way a glass surface catches a window at an angle. */
    linear-gradient(
      104deg,
      rgba(255, 255, 255, 0.34) 0%,
      rgba(255, 255, 255, 0) 32%,
      rgba(255, 255, 255, 0) 66%,
      rgba(255, 255, 255, 0.2) 100%
    ),
    /* The faint page tint the glass refracts, so it never reads as flat white. */
    linear-gradient(94deg, rgba(0, 157, 219, 0.06), rgba(255, 255, 255, 0) 45%, rgba(232, 198, 4, 0.05));
  border: 1px solid rgba(255, 255, 255, 0.62);
  /* The stack: float over the page, a bright top lip and a dim bottom one (the pane's
     thickness), then a cold halo pooling just inside the lower edge. */
  box-shadow:
    0 22px 45px -28px rgba(3, 4, 94, 0.45),
    0 3px 12px -6px rgba(3, 4, 94, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.95),
    inset 0 -1px 0 rgba(255, 255, 255, 0.55),
    inset 0 -9px 16px -12px rgba(3, 4, 94, 0.32),
    inset 0 0 0 1px rgba(255, 255, 255, 0.2);
  /* Frosted, brightened and saturated: the blur alone would only look out of focus. */
  -webkit-backdrop-filter: blur(18px) saturate(1.75) brightness(1.05);
  backdrop-filter: blur(18px) saturate(1.75) brightness(1.05);
}

/* The CSS pane's own specular band and prism edge. Both are pure light: no hit area, no
   layout - and both belong to the stand-in, since the film brings its own highlights. */
.platform-bar:not([data-soap-bubble-ready])::before,
.platform-bar:not([data-soap-bubble-ready])::after {
  content: '';
  position: absolute;
  pointer-events: none;
  border-radius: inherit;
}

.platform-bar:not([data-soap-bubble-ready])::before {
  inset: 1px 1px auto;
  height: 46%;
  /* Bulging like the top of a glass tube, so the sheen follows a curve, not a line. */
  border-radius: 999px 999px 42% 42% / 999px 999px 100% 100%;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.72) 0%,
    rgba(255, 255, 255, 0.16) 46%,
    rgba(255, 255, 255, 0) 100%
  );
}

.platform-bar:not([data-soap-bubble-ready])::after {
  inset: 0;
  /* Cool on one flank, warm on the other: the slight split light takes through glass. */
  box-shadow:
    inset 1px 0 0 rgba(0, 157, 219, 0.18),
    inset -1px 0 0 rgba(232, 198, 4, 0.16),
    inset 0 0 0 1px rgba(255, 255, 255, 0.32);
}

/* Content sits above the two light layers. */
.bar-left,
.bar-right,
.bar-title {
  position: relative;
  z-index: 1;
}

.bar-left {
  display: flex;
  align-items: center;
  min-width: 0;
}

.bar-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 14px;
  min-width: 0;
}

/* Without a backdrop filter there is nothing to see through, so the pane turns opaque
   instead of leaving the page text to show behind the header's own. */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .platform-bar:not([data-soap-bubble-ready]) {
    background-color: rgba(255, 255, 255, 0.97);
  }
}

/* The wordmark: a wide-set, quietly weighted sans, assembled one letter at a time. */
.bar-title {
  display: flex;
  justify-content: center;
  margin: 0;
  min-width: 0;
  font-family: var(--font);
  font-size: clamp(0.64rem, 1.05vw, 0.9rem);
  font-weight: 650;
  line-height: 1;
  letter-spacing: 0.16em;
  /* Trailing tracking would push the centred word off-centre. */
  text-indent: 0.16em;
  text-transform: uppercase;
  white-space: nowrap;
  color: var(--ink);
}

.glyph {
  display: inline-block;
  animation: glyph-in 0.6s var(--ease) both;
}

@keyframes glyph-in {
  from {
    opacity: 0;
    transform: translate3d(0, 0.5em, 0);
    filter: blur(5px);
  }
}

/* CURRENT SESSION: the signed-in name and the way out, the only chrome the pill keeps
   besides the countdown - the wordmark already identifies the page. */
.user-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.78em;
  font-weight: 500;
  color: var(--muted);
}

.btn-logout {
  flex: none;
  padding: 6px 14px;
  border: 1px solid rgba(239, 68, 68, 0.45);
  border-radius: 999px;
  background-color: rgba(255, 255, 255, 0.7);
  color: #d92d20;
  font-family: inherit;
  font-size: 0.72em;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background-color 0.25s ease,
    border-color 0.25s ease,
    color 0.25s ease,
    transform 0.25s var(--ease);
}

.btn-logout:hover {
  background-color: #dc2626;
  border-color: #dc2626;
  color: #ffffff;
  transform: translateY(-1px);
}

.btn-logout:active {
  transform: translateY(0);
}

/* ========================================================= DASHBOARD ==== */
.dashboard {
  position: relative;
  z-index: 1;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  width: 100%;
  max-width: 1240px;
  min-height: 0;
  margin: 0 auto;
}

/* Three columns give each panel a full-height row, so the whole brief fits without the
   page ever needing a scrollbar. */
.board {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.08fr) minmax(0, 1fr);
  gap: var(--gap);
  min-height: 0;
}

.column {
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  min-width: 0;
  min-height: 0;
}

/* ANNOUNCEMENT BAR */
.announcement-bar {
  flex: none;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: clamp(9px, 1.3vh, 13px) clamp(14px, 1.4vw, 20px);
  border: 1px solid var(--line);
  border-left: 3px solid var(--gold);
  border-radius: 14px;
  background-color: rgba(255, 255, 255, 0.9);
  box-shadow: 0 1px 2px rgba(3, 4, 94, 0.04);
  animation: panel-in 0.75s var(--ease) 0.1s both;
}

.announcement-label {
  flex: none;
  padding-top: 0.15em;
  font-size: 0.66em;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink);
}

.announcement-lines {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.announcement-text {
  color: var(--ink-2);
  font-size: 0.88em;
  line-height: 1.45;
}

/* PANELS: white cards on the tinted page, hairline edges, one soft shadow. */
.panel {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: clamp(9px, 1.3vh, 14px);
  min-width: 0;
  padding: clamp(13px, 1.9vh, 20px) clamp(14px, 1.5vw, 22px);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.99), rgba(255, 255, 255, 0.92));
  box-shadow:
    0 1px 2px rgba(3, 4, 94, 0.04),
    0 24px 48px -38px rgba(3, 4, 94, 0.45);
  transition: border-color 0.35s ease, box-shadow 0.35s ease;
  animation: panel-in 0.8s var(--ease) both;
}

.panel:hover {
  border-color: rgba(0, 157, 219, 0.28);
  box-shadow:
    0 1px 2px rgba(3, 4, 94, 0.05),
    0 28px 54px -36px rgba(3, 4, 94, 0.4);
}

@keyframes panel-in {
  from {
    opacity: 0;
    transform: translate3d(0, 14px, 0);
  }
}

/* The cards land in reading order: identity, links, the paper, then the verdict. */
.panel-delegate { --dot: var(--gold); animation-delay: 0.16s; }
.panel-links { --dot: var(--accent); animation-delay: 0.24s; }
.panel-paper { --dot: var(--ink); animation-delay: 0.3s; }
.panel-grade { --dot: var(--green); animation-delay: 0.38s; }

.panel-links {
  flex: 1;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 1.04em;
  font-weight: 650;
  line-height: 1.25;
  letter-spacing: -0.005em;
  color: var(--ink);
}

.panel-title::before {
  content: '';
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: var(--dot, var(--accent));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--dot, var(--accent)) 14%, transparent);
}

/* CONFERENCE LINKS: five quiet wells that fill the card's spare height. */
.links-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: clamp(5px, 0.8vh, 9px);
  min-height: 0;
}

.link-box {
  flex: 1;
  display: flex;
  align-items: center;
  min-height: clamp(28px, 3.4vh, 38px);
  padding: 0 11px;
  border: 1px solid transparent;
  border-radius: 11px;
  background-color: #f7fafd;
  transition:
    background-color 0.25s ease,
    border-color 0.25s ease,
    transform 0.3s var(--ease);
}

.link-box:hover {
  border-color: rgba(0, 157, 219, 0.24);
  background-color: #ffffff;
  transform: translateX(2px);
}

.link-box a {
  display: flex;
  flex-direction: column;
  gap: 1px;
  width: 100%;
  min-width: 0;
  text-decoration: none;
}

.link-name {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 0.84em;
  font-weight: 600;
  letter-spacing: 0.005em;
  color: var(--ink);
}

.link-url {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 0.74em;
  color: var(--muted);
}

.link-box a:hover .link-name {
  color: #0079ab;
}

/* DELEGATE INFO */
.info-content {
  display: flex;
  flex-direction: column;
  gap: clamp(6px, 0.9vh, 9px);
}

.info-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: clamp(7px, 1vh, 10px) 12px;
  border-radius: 11px;
  background-color: #f7fafd;
}

.info-label {
  flex: none;
  font-size: 0.68em;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.info-value {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.84em;
  font-weight: 600;
  text-align: right;
  color: var(--ink);
}

/* POSITION PAPER PANEL */
.panel-paper {
  gap: clamp(9px, 1.3vh, 13px);
}

.instructions-block {
  padding: clamp(8px, 1.1vh, 12px) 12px;
  border-radius: 12px;
  background-color: #f7fafd;
}

.instructions-list {
  margin: 0;
  padding-left: 1.15em;
  font-size: 0.82em;
  line-height: 1.5;
  color: var(--ink-2);
}

.instructions-list li + li {
  margin-top: 3px;
}

.instructions-list li::marker {
  font-weight: 600;
  color: var(--accent);
}

.status-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 12px;
  border-radius: 11px;
  background-color: #f7fafd;
}

.status-label {
  font-size: 0.68em;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.64em;
  font-weight: 700;
  letter-spacing: 0.09em;
  white-space: nowrap;
}

.status-badge::before {
  content: '';
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background-color: currentColor;
}

.status-unsubmitted {
  background-color: rgba(239, 68, 68, 0.1);
  color: #b42318;
}

.status-submitted {
  background-color: rgba(232, 198, 4, 0.18);
  color: #8a6d00;
}

.status-graded {
  background-color: rgba(22, 163, 74, 0.13);
  color: #15803d;
}

/* GRADE & FEEDBACK PANEL */
.panel-grade {
  gap: clamp(9px, 1.3vh, 14px);
}

.grade-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: clamp(16px, 2.4vh, 26px) 16px;
  border: 1px dashed rgba(3, 4, 94, 0.14);
  border-radius: 14px;
  background-color: #f7fafd;
  text-align: center;
}

.grade-empty p {
  margin: 0;
  max-width: 30ch;
  font-size: 0.82em;
  line-height: 1.5;
}

.grade-empty-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background-color: #ffffff;
  color: var(--accent);
  box-shadow:
    inset 0 0 0 1px var(--line),
    0 8px 18px -14px rgba(3, 4, 94, 0.6);
  animation: float-soft 3.6s ease-in-out infinite;
}

.grade-empty-icon svg {
  width: 18px;
  height: 18px;
}

@keyframes float-soft {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}

.grade-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: clamp(10px, 1.4vh, 14px) 14px;
  border-radius: 12px;
  background-color: #f7fafd;
}

.grade-total {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.grade-total-label {
  font-size: 0.64em;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
}

.grade-total-value {
  font-size: 1.55em;
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  color: var(--green);
}

.rubric-breakdown {
  display: flex;
  flex-direction: column;
  gap: clamp(7px, 1vh, 11px);
}

.subsection-title {
  margin: 0;
  font-size: 0.64em;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
}

.criterion-row {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.criterion-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 0.82em;
}

.criterion-label {
  color: var(--ink-2);
}

.criterion-score {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  color: var(--ink);
}

.criterion-bar-bg {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background-color: rgba(3, 4, 94, 0.08);
}

.criterion-bar-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #4ade80, var(--green));
  transform-origin: left center;
  animation: bar-grow 1.15s var(--ease) 0.5s both;
}

.criterion-bar-fill.low {
  background: linear-gradient(90deg, #f5d84a, var(--gold));
}

/* Each bar follows the one above it, so the rubric fills in like a report being read. */
.criterion-row:nth-child(2) .criterion-bar-fill { animation-delay: 0.58s; }
.criterion-row:nth-child(3) .criterion-bar-fill { animation-delay: 0.66s; }
.criterion-row:nth-child(4) .criterion-bar-fill { animation-delay: 0.74s; }
.criterion-row:nth-child(5) .criterion-bar-fill { animation-delay: 0.82s; }
.criterion-row:nth-child(6) .criterion-bar-fill { animation-delay: 0.9s; }

@keyframes bar-grow {
  from { transform: scaleX(0); }
}

.grade-muted {
  margin: 0;
  font-size: 0.8em;
  font-style: italic;
  color: #6b7c8d;
}

.feedback-block {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-height: 0;
}

.feedback-text {
  flex: 1;
  margin: 0;
  padding: 11px 13px;
  border: 1px solid rgba(3, 4, 94, 0.07);
  border-radius: 12px;
  background-color: #f7fafd;
  font-size: 0.84em;
  line-height: 1.55;
  color: var(--ink-2);
  white-space: pre-wrap;
}

/* FILE UPLOAD: pinned to the foot of the card, so the form sits level across columns. */
.upload-box {
  display: flex;
  flex-direction: column;
  gap: 9px;
  margin-top: auto;
  padding: clamp(9px, 1.2vh, 13px);
  border: 1px dashed rgba(3, 4, 94, 0.16);
  border-radius: 13px;
  background-color: #f9fbfd;
}

.upload-label {
  font-size: 0.66em;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
}

.file-input {
  max-width: 100%;
  font-family: inherit;
  font-size: 0.74em;
  color: var(--muted);
}

.file-input::file-selector-button {
  margin-right: 10px;
  padding: 6px 10px;
  border: 1px solid rgba(3, 4, 94, 0.14);
  border-radius: 8px;
  background-color: #ffffff;
  color: var(--ink);
  font-family: inherit;
  font-size: 1em;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s ease, border-color 0.2s ease;
}

.file-input::file-selector-button:hover {
  border-color: rgba(0, 157, 219, 0.4);
  background-color: #eef6fc;
}

.paper-download-block {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.btn-download-paper {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 13px;
  border: 1px solid rgba(0, 157, 219, 0.4);
  border-radius: 9px;
  background-color: #ffffff;
  color: #0079ab;
  font-family: inherit;
  font-size: 0.78em;
  font-weight: 650;
  cursor: pointer;
  transition:
    background-color 0.25s ease,
    border-color 0.25s ease,
    transform 0.25s var(--ease),
    box-shadow 0.25s ease;
}

.btn-icon {
  display: inline-flex;
}

.btn-icon svg {
  width: 13px;
  height: 13px;
}

.btn-download-paper:hover:not(:disabled) {
  border-color: var(--accent);
  background-color: #f2f9fe;
  transform: translateY(-1px);
  box-shadow: 0 10px 20px -16px rgba(0, 121, 171, 0.9);
}

.btn-download-paper:disabled {
  border-color: rgba(3, 4, 94, 0.12);
  color: #9aa5b1;
  cursor: not-allowed;
}

.download-hint {
  font-size: 0.72em;
  color: var(--muted);
}

.btn-submit {
  align-self: flex-start;
  padding: 9px 18px;
  border: 0;
  border-radius: 10px;
  background-color: var(--ink);
  color: #ffffff;
  font-family: inherit;
  font-size: 0.8em;
  font-weight: 650;
  letter-spacing: 0.01em;
  cursor: pointer;
  transition:
    background-color 0.25s ease,
    transform 0.25s var(--ease),
    box-shadow 0.25s ease;
}

.btn-submit:hover:not(:disabled) {
  background-color: #071f7a;
  transform: translateY(-1px);
  box-shadow: 0 12px 24px -16px rgba(3, 4, 94, 0.9);
}

.btn-submit:active:not(:disabled) {
  transform: translateY(0) scale(0.99);
}

.btn-submit:disabled {
  background-color: #eef2f6;
  color: #9aa5b1;
  cursor: not-allowed;
}

/* ======================================================== RESPONSIVE ==== */
/* The platform sheds its least important chrome before the title is allowed to crowd. */
@media (max-width: 900px) {
  .user-name {
    display: none;
  }
}

/* Two columns: identity and links keep the left rail, the paper and the grade stack. */
@media (max-width: 1000px) {
  .board {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .column {
    grid-row: span 2;
  }
}

@media (max-width: 768px) {
  .delegate-page {
    --gap: 10px;
  }

  .platform-bar {
    padding: 0 14px;
    gap: 10px;
  }

  .bar-right {
    gap: 10px;
  }

  .btn-logout {
    padding: 5px 10px;
  }

  .bar-countdown {
    display: none;
  }

  .board {
    grid-template-columns: minmax(0, 1fr);
  }

  .column {
    grid-row: auto;
  }
}

/* Motion is decoration here: keep the layout, drop the movement. */
@media (prefers-reduced-motion: reduce) {
  .platform-bar,
  .glyph,
  .announcement-bar,
  .panel,
  .criterion-bar-fill,
  .grade-empty-icon,
  .delegate-page::before,
  .delegate-page::after {
    animation: none;
  }

  .btn-logout,
  .link-box,
  .btn-download-paper,
  .btn-submit {
    transition: none;
  }
}
</style>
