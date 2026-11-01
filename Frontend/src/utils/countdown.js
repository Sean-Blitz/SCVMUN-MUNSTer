/**
 * Countdown arithmetic for the header timer, kept out of the component so it can be
 * exercised with plain Node (see the check in the report) without a browser or a build.
 *
 * Units are days / hours / minutes / seconds. "Months" is deliberately not a unit: a month
 * has no fixed length, so a countdown that showed them would jump at odd moments - and it
 * would still have to show days underneath.
 */

/** Two-digit padding for the clock-style parts. */
export function pad(value) {
  return String(value).padStart(2, '0')
}

/**
 * What is left between `now` and `target`.
 *
 * Returns null when the target is unusable (missing, or not a date), so callers can hide
 * the timer instead of rendering `NaN`. Returns `{ live: true }` with every part at zero
 * once the target has passed.
 */
export function remainingParts(target, now = new Date()) {
  const targetMs = target instanceof Date ? target.getTime() : new Date(target ?? '').getTime()
  if (Number.isNaN(targetMs)) return null

  const ms = targetMs - now.getTime()
  if (ms <= 0) return { live: true, days: 0, hours: 0, minutes: 0, seconds: 0 }

  const total = Math.floor(ms / 1000)
  return {
    live: false,
    days: Math.floor(total / 86400),
    hours: Math.floor((total % 86400) / 3600),
    minutes: Math.floor((total % 3600) / 60),
    seconds: total % 60
  }
}

/** "3d 04h 09m 12s" - the compact form the header shows. */
export function formatRemaining(parts) {
  if (!parts) return ''
  if (parts.live) return 'Conference is Live!'
  return `${parts.days}d ${pad(parts.hours)}h ${pad(parts.minutes)}m ${pad(parts.seconds)}s`
}
