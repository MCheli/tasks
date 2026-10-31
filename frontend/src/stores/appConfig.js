import { defineStore } from 'pinia'
import * as authApi from '@/api/auth'

let pending = null

/** What the server says about this deployment (Google sign-in, demo mode). Loaded once per page load. */
export const useAppConfigStore = defineStore('appConfig', {
  state: () => ({
    config: null,
  }),
  getters: {
    loaded: (state) => state.config !== null,
    demo: (state) => state.config?.demo_mode ?? false,
    demoUrl: (state) => state.config?.demo_url ?? null,
    googleConfigured: (state) => state.config?.google_configured ?? false,
  },
  actions: {
    load() {
      if (!pending) {
        pending = authApi
          .config()
          .then(({ data }) => (this.config = data))
          .catch(() => {
            pending = null
            this.config = { google_configured: false, demo_mode: false, demo_url: null }
          })
      }
      return pending
    },
  },
})
