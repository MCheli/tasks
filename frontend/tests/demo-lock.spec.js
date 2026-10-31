import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, withDirectives } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { DEMO_LOCK_TITLE, vDemoLock } from '@/directives/demoLock'
import { useAppConfigStore } from '@/stores/appConfig'

function mountButton(onClick) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const Comp = defineComponent({
    setup: () => () => withDirectives(h('button', { onClick }, 'Add task'), [[vDemoLock]]),
  })
  return { wrapper: mount(Comp, { global: { plugins: [pinia] } }), cfg: useAppConfigStore() }
}

const config = (demo) => ({ google_configured: false, demo_mode: demo, demo_url: null })

describe('v-demo-lock', () => {
  it('leaves controls alone outside the demo', async () => {
    const onClick = vi.fn()
    const { wrapper, cfg } = mountButton(onClick)
    cfg.config = config(false)
    await nextTick()
    const btn = wrapper.get('button')
    expect(btn.attributes('disabled')).toBeUndefined()
    await btn.trigger('click')
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('disables a control that writes in the demo, says why, and swallows clicks', async () => {
    const onClick = vi.fn()
    const { wrapper, cfg } = mountButton(onClick)
    cfg.config = config(true)
    await nextTick()
    const btn = wrapper.get('button')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.attributes('aria-disabled')).toBe('true')
    expect(btn.attributes('title')).toBe(DEMO_LOCK_TITLE)
    expect(btn.classes()).toContain('demo-locked')
    btn.element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(onClick).not.toHaveBeenCalled()
  })

  it('unlocks if the config turns out not to be the demo', async () => {
    const { wrapper, cfg } = mountButton(() => {})
    cfg.config = config(true)
    await nextTick()
    cfg.config = config(false)
    await nextTick()
    const btn = wrapper.get('button')
    expect(btn.attributes('disabled')).toBeUndefined()
    expect(btn.classes()).not.toContain('demo-locked')
  })
})
