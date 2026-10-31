import { watchEffect } from 'vue'
import { useAppConfigStore } from '@/stores/appConfig'

export const DEMO_LOCK_TITLE = 'Not available in the demo: nothing can be changed or saved'

function apply(el, on) {
  if (on) {
    el.setAttribute('disabled', '')
    el.setAttribute('aria-disabled', 'true')
    el.setAttribute('title', DEMO_LOCK_TITLE)
    el.classList.add('demo-locked')
  } else if (el.classList.contains('demo-locked')) {
    el.removeAttribute('disabled')
    el.removeAttribute('aria-disabled')
    el.removeAttribute('title')
    el.classList.remove('demo-locked')
  }
}

/**
 * v-demo-lock on anything that changes data: in the public demo it is disabled with an
 * explanation instead of failing after a click. The server refuses those writes regardless
 * (backend app/demo.py); this is for honesty and polish.
 */
export const vDemoLock = {
  mounted(el) {
    const cfg = useAppConfigStore()
    el._demoBlock = (e) => {
      if (cfg.demo) {
        e.preventDefault()
        e.stopImmediatePropagation()
      }
    }
    el.addEventListener('click', el._demoBlock, true)
    el._demoStop = watchEffect(() => apply(el, cfg.demo))
  },
  updated(el) {
    // Vue re-renders `:disabled` bindings; put the lock back on top.
    apply(el, useAppConfigStore().demo)
  },
  beforeUnmount(el) {
    el._demoStop?.()
    if (el._demoBlock) el.removeEventListener('click', el._demoBlock, true)
  },
}
