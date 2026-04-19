import { onMounted, onUnmounted } from 'vue'

/**
 * Bind keyboard shortcuts. `handlers` is a map of:
 *   'n'         → fn
 *   'g c'       → fn (chord — second key within 1.2s of first)
 *   'mod+enter' → fn  (ctrlKey on win/linux, metaKey on mac)
 *
 * Shortcuts do not fire while the target is INPUT/TEXTAREA/SELECT
 * unless `fn.allowInInput` is truthy.
 */
export function useKeyboardShortcuts(handlers) {
  let chordPrefix = ''
  let chordTimer = null

  function reset() {
    chordPrefix = ''
    if (chordTimer) {
      clearTimeout(chordTimer)
      chordTimer = null
    }
  }

  function onKey(e) {
    const target = e.target
    const inField =
      target &&
      (target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable)

    const mod = e.ctrlKey || e.metaKey
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase()
    const combo = `${mod ? 'mod+' : ''}${key}`

    // Try chord first (e.g. "g c")
    if (chordPrefix) {
      const chordKey = `${chordPrefix} ${key}`
      const fn = handlers[chordKey]
      reset()
      if (fn && (!inField || fn.allowInInput)) {
        e.preventDefault()
        fn(e)
        return
      }
    }

    // Single-key or modified
    const fn = handlers[combo]
    if (fn && (!inField || fn.allowInInput)) {
      e.preventDefault()
      fn(e)
      return
    }

    // Begin a new chord prefix (only for plain letter without modifier).
    if (!mod && /^[a-z]$/.test(key) && Object.keys(handlers).some((k) => k.startsWith(`${key} `))) {
      if (inField) return
      chordPrefix = key
      chordTimer = setTimeout(reset, 1200)
    }
  }

  onMounted(() => window.addEventListener('keydown', onKey))
  onUnmounted(() => window.removeEventListener('keydown', onKey))
}
