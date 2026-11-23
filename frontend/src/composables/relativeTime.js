/** "just now", "5m ago", "3h ago", "2d ago", else a short date. */
export function relativeTime(iso, now = Date.now()) {
  if (!iso) return ''
  const ms = now - new Date(iso).getTime()
  const sec = Math.floor(ms / 1000)
  if (sec < 45) return 'just now'
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.floor(hr / 24)
  if (day < 14) return `${day}d ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/** "Nov 23, 6:04 PM" for log entries. */
export function fmtDateTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}
