<template>
  <!-- PLATFORM: the rounded capsule that owns the top of a role dashboard: countdown on the
       left, the wordmark in the centre, session details on the right. -->
  <header class="platform-bar">
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
</template>

<script setup>
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useLogout } from '@/utils/useLogout'
import ConferenceCountdown from '@/components/ConferenceCountdown.vue'

const authStore = useAuthStore()
const { handleLogout } = useLogout()

// The bar shows who is signed in, exactly as the shell's navbar used to.
const currentUser = computed(() => authStore.user || { name: 'Guest', role: 'none' })

// ---------- Wordmark (presentation only) ----------
// The title assembles itself a letter at a time on load. Each glyph carries its own delay,
// so no timer runs in the script once the page has mounted.
const TITLE = 'SCVMUN Munster'

// Spacing glyphs keep their width as flex items, so words keep their gaps.
const titleGlyphs = TITLE.split('').map((char) => (char === ' ' ? '\u00A0' : char))
</script>

<style scoped>
/* The bar carries its own tokens, so it reads the same inside the shell as it does on the
   delegate dashboard, where these came from the page. */
.platform-bar {
  --ink: #03045e;
  --muted: #63708c;
  --line: rgba(3, 4, 94, 0.09);
  --ease: cubic-bezier(0.22, 1, 0.36, 1);
  --font: var(--font-theme);

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
  /* PLAIN WHITE: a flat surface like the rest of the page - no film, nothing that follows
     the pointer. */
  background: #ffffff;
  border: 1px solid var(--line);
  border-radius: 999px;
  box-shadow: 0 14px 30px -26px rgba(3, 4, 94, 0.4);
  font-family: var(--font);
  /* The delegate page sized the bar's em units with its own page scale; keep that scale
     here so the component renders identically in the shell and on that page. */
  font-size: clamp(0.85rem, 1.6vh, 1rem);
  color: var(--muted);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  animation: bar-in 0.85s var(--ease) both;
}

@keyframes bar-in {
  from {
    opacity: 0;
    transform: translate3d(0, -14px, 0);
  }
}

/* Columns of the bar. */
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

/* The wordmark: a wide-set, quietly weighted sans, assembled one letter at a time. */
.bar-title {
  display: flex;
  justify-content: center;
  margin: 0;
  min-width: 0;
  font-family: var(--font);
  font-size: clamp(0.74rem, 1.05vw, 0.92rem);
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.14em;
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
  }
}

/* CURRENT SESSION: the signed-in name and the way out, the only chrome the pill keeps
   besides the countdown - the wordmark already identifies the page. */
.user-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.86em;
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
  font-size: 0.78em;
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

/* ======================================================== RESPONSIVE ==== */
/* The platform sheds its least important chrome before the title is allowed to crowd. */
@media (max-width: 900px) {
  .user-name {
    display: none;
  }
}

@media (max-width: 768px) {
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
}

/* Motion is decoration here: keep the layout, drop the movement. */
@media (prefers-reduced-motion: reduce) {
  .platform-bar,
  .glyph {
    animation: none;
  }

  .btn-logout {
    transition: none;
  }
}
</style>
