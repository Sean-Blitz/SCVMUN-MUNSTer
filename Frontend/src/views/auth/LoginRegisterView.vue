<template>
  <div class="page-container" ref="pageEl">
    <!-- INTRO: the typed wordmark, pinned while the page scrolls -->
    <section class="intro-stage">
      <div class="intro-pin">
        <h1 class="typed-title" aria-label="SCVMUN Homepage">
          <span
            v-for="(glyph, index) in typedGlyphs"
            :key="index"
            class="glyph"
            :style="glyph.style"
            aria-hidden="true"
          >{{ glyph.char }}</span>
          <span class="caret" aria-hidden="true"></span>
        </h1>

        <span class="scroll-cue" aria-hidden="true"></span>
      </div>
    </section>

    <main class="panel">
      <div class="auth-card">
        <img
          src="@/assets/logo-mark.png"
          alt="SCVMUN Logo"
          class="panel-logo"
        />
        <h2>Account Access</h2>
        
        <form @submit.prevent class="auth-form">
          <div class="input-group">
            <span class="icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
                   stroke-width="1.6" stroke-linecap="round">
                <path d="M9.2 4.6 7.7 19.4" />
                <path d="M16.3 4.6 14.8 19.4" />
                <path d="M4.7 9.2h14.6" />
                <path d="M4.4 14.8h14.6" />
              </svg>
            </span>
            <input 
              type="text" 
              v-model="userHash" 
              placeholder="Hash / Access Code" 
              required
            />
          </div>

          <div class="input-group">
            <span class="icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
                   stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                <rect x="5" y="10.6" width="14" height="9.4" rx="2.6" />
                <path d="M8.6 10.6V8.2a3.4 3.4 0 0 1 6.8 0v2.4" />
                <path d="M12 14.2 13.3 15.8 12 17.4 10.7 15.8Z" fill="currentColor" stroke="none" />
              </svg>
            </span>
            <input 
              type="password" 
              v-model="userPassword" 
              placeholder="Password" 
              required
            />
          </div>

          <div v-if="captchaEnabled" class="captcha-group">
            <div ref="captchaContainer" class="captcha-widget"></div>
            <p v-if="captchaError" class="captcha-error">{{ captchaError }}</p>
          </div>

          <div class="button-group">
            <SoapBubbleButton
              class="btn-glass btn-glass-primary"
              :disabled="isLoading || captchaPending"
              :material="loginMaterial"
              :backdrop="pageEl"
              @click="handleLogin"
            >
              Log In
            </SoapBubbleButton>

            <SoapBubbleButton
              class="btn-glass"
              :disabled="isLoading || captchaPending"
              :material="registerMaterial"
              :backdrop="pageEl"
              @click="handleRegister"
            >
              First-Time Register
            </SoapBubbleButton>
          </div>
        </form>

        <p class="registration-note">
          Click <strong>First-Time Register</strong> to create your account using the hash you received from your advisor. Afterwards, you can use the password you set above to log in again.
        </p>

        <p class="forgot-password">
          Forgot Password? Email sg@scvmun.com to reset it.
        </p>
      </div>

      <p class="page-note">
        Your access code/hash is confidential. Do not share it with other delegates!
        If you do not yet have your access code, talk with your advisor.
        Good luck on conference day!
      </p>
    </main>

    <!-- Black specks: fixed above everything, so they cross onto the panel as it rises
         and fade out instead of disappearing behind it. -->
    <div class="specks" aria-hidden="true">
      <span
        v-for="(speck, index) in specks"
        :key="index"
        class="speck"
        :style="speck.orbit"
      >
        <span class="speck-dot"></span>
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import SoapBubbleButton from '@/components/soap-bubble/SoapBubbleButton.vue'

const router = useRouter()
const authStore = useAuthStore()
const toastStore = useToastStore()

// Unified reactive state for both actions
const userHash = ref('')
const userPassword = ref('')
const isLoading = ref(false)

// Soap-bubble material: the approved light-glass preset (the page is white) plus the
// catalogue preview's lighting and reflection settings.
const bubbleGlass = {
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
  // Upright outer window, inverted inner reflection, no glint, no twin window.
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
  bottomShadeColor: '#ffffff'
}

// Log In carries the primary weight by tinting the same film navy; Register stays clear.
const loginMaterial = { ...bubbleGlass, tint: '#03045e', opacity: 0.82 }
const registerMaterial = { ...bubbleGlass }

// ---------- Human check (Cloudflare Turnstile) ----------
// The site key is public and baked in at build time, so leaving it unset disables the
// widget completely - which is how development runs, matching the backend's behaviour
// when TURNSTILE_SECRET_KEY is absent.
const turnstileSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY || ''
const captchaEnabled = Boolean(turnstileSiteKey)
const TURNSTILE_SCRIPT = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

const captchaContainer = ref(null)
const captchaToken = ref('')
const captchaWidgetId = ref(null)
const captchaError = ref('')

// Turnstile tokens are single-use and expire after 5 minutes, so a submission needs one
// that this page has just obtained: until the callback fires there is nothing to send.
const captchaPending = computed(() => captchaEnabled && !captchaToken.value)

let scriptPromise = null

const loadTurnstile = () => {
  if (window.turnstile) return Promise.resolve()
  if (scriptPromise) return scriptPromise

  scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = TURNSTILE_SCRIPT
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Turnstile failed to load'))
    document.head.appendChild(script)
  })

  return scriptPromise
}

const renderCaptcha = () => {
  if (!captchaEnabled || !window.turnstile || !captchaContainer.value) return

  captchaWidgetId.value = window.turnstile.render(captchaContainer.value, {
    sitekey: turnstileSiteKey,
    theme: 'light',
    // Must match captcha.ACTION in the backend: Siteverify echoes this back and the server
    // rejects a token minted for any other action.
    action: 'auth',
    // Stays out of the way unless Cloudflare decides an interactive challenge is needed.
    appearance: 'interaction-only',
    // Fetch a fresh token when the old one expires behind the five-minute limit.
    'refresh-expired': 'auto',
    callback: (token) => {
      captchaToken.value = token
      captchaError.value = ''
    },
    'expired-callback': () => { captchaToken.value = '' },
    'timeout-callback': () => { captchaToken.value = '' },
    'error-callback': () => {
      captchaToken.value = ''
      captchaError.value = 'The human check failed to run. Please refresh the page.'
    }
  })
}

// A failed submit has consumed the token (they are single-use), so the next attempt needs
// a fresh one. Safe to call on any error, including a network failure.
const resetCaptcha = () => {
  captchaToken.value = ''
  if (captchaWidgetId.value !== null && window.turnstile) {
    window.turnstile.reset(captchaWidgetId.value)
  }
}

const captchaHeaders = () =>
  captchaEnabled && captchaToken.value ? { 'X-Turnstile-Token': captchaToken.value } : {}

onMounted(async () => {
  if (!captchaEnabled) return
  try {
    await loadTurnstile()
    renderCaptcha()
  } catch (error) {
    captchaError.value = 'The human check could not load. Please refresh the page.'
  }
})

onBeforeUnmount(() => {
  if (captchaWidgetId.value !== null && window.turnstile) {
    window.turnstile.remove(captchaWidgetId.value)
  }
})

// ---------- Intro animation (presentation only) ----------
// The wordmark types itself in, then breaks apart as the page scrolls. Scroll progress is
// written straight to a CSS custom property (`--p`) so the animation never re-renders Vue.
const TITLE = 'SCVMUN Homepage'
const pageEl = ref(null)
const typedCount = ref(0)

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// Each glyph gets its own drift, so the word shatters into uneven pieces rather than
// sliding away as one block.
const glyphs = TITLE.split('').map((char) => ({
  char: char === ' ' ? '\u00A0' : char,
  style: {
    '--dx': `${((Math.random() - 0.5) * 280).toFixed(1)}px`,
    '--dy': `${((Math.random() - 0.15) * 240).toFixed(1)}px`,
    '--rot': `${((Math.random() - 0.5) * 110).toFixed(1)}deg`,
    '--lag': (0.6 + Math.random() * 0.7).toFixed(2),
    '--blur': (1 + Math.random() * 3).toFixed(2)
  }
}))

const specks = Array.from({ length: 26 }, (_, index) => {
  const angle = (index / 26) * Math.PI * 2 + Math.random() * 0.35
  const radius = 70 + Math.random() * 210
  return {
    orbit: {
      '--sx': `${(Math.cos(angle) * radius).toFixed(1)}px`,
      '--sy': `${(Math.sin(angle) * radius).toFixed(1)}px`,
      '--size': `${(2 + Math.random() * 4).toFixed(1)}px`,
      '--dur': `${(7 + Math.random() * 9).toFixed(2)}s`,
      '--delay': `${(-Math.random() * 9).toFixed(2)}s`
    }
  }
})

const typedGlyphs = computed(() => glyphs.slice(0, typedCount.value))

let typeTimer = null
let scrollFrame = 0

const paintProgress = () => {
  scrollFrame = 0
  const page = pageEl.value
  if (!page) return
  const viewport = window.innerHeight || 1
  const progress = Math.min(1, Math.max(0, window.scrollY / (viewport * 0.55)))
  page.style.setProperty('--p', progress.toFixed(4))
}

// One rAF-coalesced handler: scroll fires far more often than frames.
const onScroll = () => {
  if (!scrollFrame) scrollFrame = requestAnimationFrame(paintProgress)
}

onMounted(() => {
  if (prefersReducedMotion()) {
    typedCount.value = glyphs.length
    return
  }

  // Uneven keystroke rhythm, the way a real typewriter sounds.
  const type = () => {
    typedCount.value += 1
    if (typedCount.value < glyphs.length) {
      typeTimer = setTimeout(type, 70 + Math.random() * 90)
    }
  }
  typeTimer = setTimeout(type, 320)

  paintProgress()
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll)
})

onBeforeUnmount(() => {
  clearTimeout(typeTimer)
  if (scrollFrame) cancelAnimationFrame(scrollFrame)
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('resize', onScroll)
})

const handleLogin = async () => {
  if (!userHash.value || !userPassword.value) {
    toastStore.showToast('Please enter both your hash and password.', 'error')
    return
  }
  if (captchaPending.value) {
    toastStore.showToast('Please complete the human check first.', 'error')
    return
  }

  isLoading.value = true
  try {
    // 1. Send credentials to backend login endpoint
    const response = await apiClient.post(
      '/auth/login',
      { hash: userHash.value, password: userPassword.value },
      { headers: captchaHeaders() }
    )

    // 2. Extract returned user and token
    const { user, token } = response.data

    // 3. Save session into Pinia Auth Store
    authStore.setAuth(user, token)

    toastStore.showToast(`Welcome back, ${user.name || 'User'}!`, 'success')

    // 4. Redirect based on their role
    router.push(`/${user.role}/dashboard`)
  } catch (error) {
    // Backend error message will automatically trigger via the global Toast Interceptor
    resetCaptcha()
  } finally {
    isLoading.value = false
  }
}

const handleRegister = async () => {
  if (!userHash.value || !userPassword.value) {
    toastStore.showToast('Please enter both your hash and password.', 'error')
    return
  }
  if (captchaPending.value) {
    toastStore.showToast('Please complete the human check first.', 'error')
    return
  }

  isLoading.value = true
  try {
    // 1. Send registration payload to backend
    const response = await apiClient.post(
      '/auth/register',
      { hash: userHash.value, password: userPassword.value },
      { headers: captchaHeaders() }
    )

    const { user, token } = response.data

    // 2. Save session into Pinia Auth Store
    authStore.setAuth(user, token)

    toastStore.showToast('Account registered successfully!', 'success')

    // 3. Redirect to role portal
    router.push(`/${user.role}/dashboard`)
  } catch (error) {
    // Backend error message handles popup automatically
    resetCaptcha()
  } finally {
    isLoading.value = false
  }
}
</script>

<style scoped>
/* GENERAL LAYOUT */
.page-container {
  --p: 0; /* scroll progress 0 -> 1, written by the scroll handler */
  min-height: 100vh;
  background-color: #ffffff;
  color: #03045e;
  font-family: Arial, Helvetica, sans-serif;
}

/* ---------- INTRO: the pinned typing stage ---------- */
.intro-stage {
  position: relative;
  height: 160vh;
}

.intro-pin {
  position: sticky;
  top: 0;
  z-index: 1;
  height: 100vh;
  height: 100svh;
  display: grid;
  place-items: center;
  overflow: hidden;
  padding: 0 24px;
}

.typed-title {
  margin: 0;
  display: inline-flex;
  flex-wrap: wrap;
  justify-content: center;
  font-family: 'Special Elite', 'Courier New', monospace;
  font-size: clamp(1.9rem, 6.2vw, 4.4rem);
  font-weight: 400;
  line-height: 1.25;
  letter-spacing: 0.02em;
  text-align: center;
  color: #03045e;
}

/* Each character is its own piece: it drifts off, spins, blurs and fades with `--p`. */
.glyph {
  display: inline-block;
  will-change: transform, opacity, filter;
  transform:
    translate3d(
      calc(var(--dx) * var(--p) * var(--lag)),
      calc(var(--dy) * var(--p) * var(--lag)),
      0
    )
    rotate(calc(var(--rot) * var(--p) * var(--lag)))
    scale(calc(1 - 0.18 * var(--p)));
  opacity: calc(1 - var(--p) * 1.2);
  filter: blur(calc(var(--p) * var(--blur) * 1px));
}

.caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 6px;
  vertical-align: -0.1em;
  background-color: #03045e;
  animation: caret-blink 1.05s steps(2, start) infinite;
  /* Fades with the title even though the blink animation owns `opacity`. */
  filter: opacity(calc(1 - var(--p) * 1.2));
}

@keyframes caret-blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

/* Black specks orbiting the wordmark. Fixed and above the panel (z-index 3), so they
   travel over the rising sheet rather than being painted out by it. */
.specks {
  position: fixed;
  inset: 0;
  z-index: 3;
  pointer-events: none;
  overflow: hidden;
}

.speck {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 0;
  height: 0;
  animation: orbit var(--dur) linear infinite;
  animation-delay: var(--delay);
  will-change: transform;
}

.speck-dot {
  position: absolute;
  width: var(--size);
  height: var(--size);
  border-radius: 50%;
  background-color: #0b0b0b;
  transform:
    translate3d(
      calc(var(--sx) * (0.35 + var(--p) * 0.9)),
      calc(var(--sy) * (0.35 + var(--p) * 0.9)),
      0
    )
    scale(calc(0.5 + var(--p) * 1.1));
  /* Fade in as the title starts to break, then fade back out over the last 60% of the
     scroll, so the specks dissolve instead of lingering over the form. */
  opacity: calc(min(1, var(--p) * 2.6) * (1 - max(0, var(--p) - 0.4) * 1.6667));
}

@keyframes orbit {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.scroll-cue {
  position: absolute;
  bottom: 34px;
  left: 50%;
  width: 13px;
  height: 13px;
  margin-left: -6px;
  border-right: 1.5px solid rgba(3, 4, 94, 0.35);
  border-bottom: 1.5px solid rgba(3, 4, 94, 0.35);
  transform: rotate(45deg);
  animation: cue-bob 1.9s ease-in-out infinite;
  opacity: calc(0.9 - var(--p) * 3);
}

@keyframes cue-bob {
  0%, 100% { transform: rotate(45deg) translate(0, 0); }
  50% { transform: rotate(45deg) translate(4px, 4px); }
}

/* ---------- PANEL: the account access card, rising over the intro ---------- */
.panel {
  position: relative;
  z-index: 2;
  margin-top: -50vh;
  min-height: 100vh;
  padding: 72px 24px 56px;
  background-color: #ffffff;
  border-radius: 32px 32px 0 0;
  /* Neutral, barely-there edge: enough to read the sheet lifting, no colour on white. */
  box-shadow: 0 -18px 60px rgba(0, 0, 0, 0.05);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.panel-logo {
  position: relative;
  z-index: 1;
  display: block;
  width: 84px;
  height: auto;
  margin: 0 auto 26px;
  filter: drop-shadow(0 6px 14px rgba(3, 4, 94, 0.18));
}

/* FORM COLUMN - borderless, so it floats on the panel */
.auth-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 440px;
  margin-bottom: 56px;
  background-color: transparent;
  padding: 0;
  border: none;
  border-radius: 0;
  box-shadow: none;
}

.auth-card h2 {
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  text-align: center;
  letter-spacing: 0.2em;
  margin: 0 0 34px;
  color: rgba(3, 4, 94, 0.5);
}

/* FORMS & INPUTS */
.auth-form {
  display: flex;
  flex-direction: column;
  gap: 26px;
}

/* Underline fields: no fill, no outline box, blue accent on focus. */
.input-group {
  display: flex;
  align-items: center;
  gap: 12px;
  background-color: transparent;
  border: none;
  border-bottom: 1px solid rgba(3, 4, 94, 0.18);
  border-radius: 0;
  padding: 10px 2px;
  transition: border-color 0.2s ease;
}

.input-group:focus-within {
  border-bottom-color: #023e8a;
}

.input-group input {
  flex: 1;
  background: transparent;
  border: none;
  color: #03045e;
  padding-left: 0;
  font-size: 1.02rem;
  letter-spacing: 0.01em;
}

.input-group input:focus {
  outline: none;
}

.input-group input::placeholder {
  color: rgba(3, 4, 94, 0.4);
}

/* Field marks are drawn, not typed: one line-icon family, currentColor. */
.icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 17px;
  height: 17px;
  color: rgba(3, 4, 94, 0.42);
  transition: color 0.2s ease;
}

.icon svg {
  display: block;
}

.input-group:focus-within .icon {
  color: #023e8a;
}

/* BUTTON GROUP (SIDE-BY-SIDE) */
.button-group {
  display: flex;
  gap: 12px;
  margin-top: 10px;
}

/* Bubble buttons: layout and label only. The film, its wobble and its press
   squash are drawn by the soap-bubble renderer on the button's own canvas. */
.btn-glass {
  flex: 1;
  min-height: 52px;
  padding: 0 22px;
  font-size: 0.95rem;
  letter-spacing: 0.02em;
  color: #03045e;
}

.btn-glass-primary {
  color: #ffffff;
}

.captcha-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.captcha-error {
  margin: 0;
  color: #b42318;
  font-size: 0.85rem;
  text-align: center;
}

/* CONTEXT TEXT */
.registration-note {
  margin-top: 30px;
  font-size: 0.85rem;
  color: rgba(3, 4, 94, 0.6);
  text-align: center;
  line-height: 1.6;
}

.registration-note strong {
  color: #03045e;
}

.forgot-password {
  margin-top: 14px;
  text-align: center;
  font-size: 0.85rem;
  color: rgba(3, 4, 94, 0.45);
}

/* NOTE AT THE FOOT OF THE PANEL */
.page-note {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 560px;
  /* `auto` keeps the note at the foot of the panel on tall screens. */
  margin: auto auto 0;
  padding-top: 26px;
  border-top: 1px solid rgba(3, 4, 94, 0.1);
  font-size: 0.82rem;
  line-height: 1.75;
  text-align: center;
  color: rgba(3, 4, 94, 0.62);
}

/* Responsive adjustment for small screens */
@media (max-width: 640px) {
  .button-group {
    flex-direction: column;
  }

  .panel {
    padding: 48px 20px 44px;
    border-radius: 24px 24px 0 0;
  }

  .panel-logo {
    width: 68px;
  }

  .typed-title {
    font-size: clamp(1.55rem, 8.6vw, 2.4rem);
  }
}

/* Motion is decoration here: drop to the static layout when it is not wanted. */
@media (prefers-reduced-motion: reduce) {
  .intro-stage {
    height: 100vh;
  }

  .intro-pin {
    position: relative;
    height: auto;
    min-height: 100vh;
  }

  .glyph,
  .caret {
    animation: none;
    opacity: 1;
    filter: none;
    transform: none;
  }

  .speck,
  .scroll-cue {
    display: none;
  }

  .panel {
    margin-top: 0;
  }
}
</style>

<style>
/* Self-hosted typewriter face, so the title needs no external font request. */
@font-face {
  font-family: 'Special Elite';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url('@/assets/fonts/special-elite-400.woff2') format('woff2');
}
</style>