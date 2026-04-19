import { defineStore } from 'pinia'
import * as authApi from '@/api/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    initialized: false,
  }),
  actions: {
    async init() {
      try {
        const { data } = await authApi.me()
        this.user = data
      } catch {
        this.user = null
      } finally {
        this.initialized = true
      }
    },
    async login(email, password) {
      const { data } = await authApi.login(email, password)
      this.user = data.user
    },
    async logout() {
      try {
        await authApi.logout()
      } finally {
        this.user = null
      }
    },
  },
})
