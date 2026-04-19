<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/api/client'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const email = ref('')
const password = ref('')
const submitting = ref(false)
const error = ref('')
const googleConfigured = ref(false)

onMounted(async () => {
  // If we're already logged in, jump straight to the next route.
  if (!auth.initialized) await auth.init()
  if (auth.user) {
    router.replace(route.query.next || '/cycle')
    return
  }
  // Find out whether the Google SSO button should be enabled.
  try {
    const { data } = await api.get('/auth/google/status')
    googleConfigured.value = data.configured
  } catch {
    googleConfigured.value = false
  }
})

async function submit() {
  if (submitting.value) return
  error.value = ''
  submitting.value = true
  try {
    await auth.login(email.value.trim(), password.value)
    router.replace(route.query.next || '/cycle')
  } catch (e) {
    if (e.response?.status === 401) {
      error.value = 'Invalid email or password.'
    } else if (e.response?.status === 422 || e.response?.status === 400) {
      error.value = 'Please enter a valid email and password.'
    } else {
      error.value = 'Something went wrong. Please try again.'
    }
  } finally {
    submitting.value = false
  }
}

function googleLogin() {
  if (!googleConfigured.value) return
  window.location.href = '/api/auth/google/login'
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 p-4 safe-bottom">
    <div class="w-full max-w-sm">
      <h1 class="text-2xl font-semibold text-center mb-6">Tasks</h1>

      <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <form @submit.prevent="submit" class="space-y-3">
          <label class="block">
            <span class="text-xs font-medium text-gray-700">Email</span>
            <input
              v-model="email"
              type="email"
              autocomplete="email"
              required
              autofocus
              class="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-accent-500 focus:outline-none"
            />
          </label>

          <label class="block">
            <span class="text-xs font-medium text-gray-700">Password</span>
            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              required
              class="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-accent-500 focus:outline-none"
            />
          </label>

          <p v-if="error" class="text-xs text-red-600" role="alert">{{ error }}</p>

          <button
            type="submit"
            :disabled="submitting"
            class="w-full rounded bg-accent-500 text-white px-4 py-2 text-sm font-medium hover:bg-accent-600 transition-colors disabled:opacity-60"
          >
            {{ submitting ? 'Signing in…' : 'Sign in' }}
          </button>
        </form>

        <div class="my-4 flex items-center gap-2 text-xs text-gray-400">
          <div class="flex-1 h-px bg-gray-200"></div>
          <span>or</span>
          <div class="flex-1 h-px bg-gray-200"></div>
        </div>

        <button
          type="button"
          @click="googleLogin"
          :disabled="!googleConfigured"
          :title="googleConfigured ? '' : 'Google SSO not yet configured by admin'"
          class="w-full rounded border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Sign in with Google
        </button>
      </div>

      <p class="text-center text-xs text-gray-400 mt-4">
        Self-hosted at tasks.markcheli.com
      </p>
    </div>
  </div>
</template>
