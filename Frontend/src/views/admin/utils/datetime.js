/**
 * The two conversions every datetime-local input needs.
 *
 * The API speaks naive UTC; `<input type="datetime-local">` speaks local wall-clock time
 * with no offset. These translate between the two, and exist in one place because both the
 * Timeline and Delegate Content tabs edit datetimes.
 */

/** naive-UTC ISO from the API -> the "YYYY-MM-DDTHH:mm" a datetime-local input wants. */
export function toLocalInput(utcIso) {
  const date = new Date(`${utcIso}Z`)
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** The reverse: a datetime-local value (local time) -> naive-UTC ISO for the API. */
export function toUtcIso(localValue) {
  const date = new Date(localValue)
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}T${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:00`
}
