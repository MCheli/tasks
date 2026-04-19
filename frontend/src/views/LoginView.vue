<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
const googleStatusLoaded = ref(false)

onMounted(async () => {
  if (!auth.initialized) await auth.init()
  if (auth.user) {
    router.replace(route.query.next || '/cycle')
    return
  }
  try {
    const { data } = await api.get('/auth/google/status')
    googleConfigured.value = data.configured
  } catch {
    googleConfigured.value = false
  } finally {
    googleStatusLoaded.value = true
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
      <h1 class="text-2xl font-semibold text-center mb-6">
        Tasks
      </h1>

      <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <!-- Skeleton placeholder while we ask the server about Google config. -->
        <div
          v-if="!googleStatusLoaded"
          class="h-10 rounded bg-gray-100 animate-pulse"
        />

        <!-- Google SSO is the only path when configured. -->
        <template v-else-if="googleConfigured">
          <p class="text-xs text-gray-500 text-center mb-4">
            Sign in with your Google account to continue.
          </p>
          <button
            type="button"
            class="w-full inline-flex items-center justify-center gap-3 rounded border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            @click="googleLogin"
          >
            <!-- Google "G" mark — official multi-color SVG. -->
            <svg
              aria-hidden="true"
              class="w-5 h-5"
              viewBox="0 0 48 48"
            >
              <path
                fill="#FFC107"
                d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z"
              />
              <path
                fill="#FF3D00"
                d="M6.306 14.691l6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z"
              />
              <path
                fill="#4CAF50"
                d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238C29.211 35.091 26.715 36 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z"
              />
              <path
                fill="#1976D2"
                d="M43.611 20.083H42V20H24v8h11.303c-.792 2.237-2.231 4.166-4.087 5.571.001-.001.002-.001.003-.002l6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z"
              />
            </svg>
            Continue with Google
          </button>
        </template>

        <!-- Fallback: password form when Google isn't configured. -->
        <template v-else>
          <form
            class="space-y-3"
            @submit.prevent="submit"
          >
            <label class="block">
              <span class="text-xs font-medium text-gray-700">Email</span>
              <input
                v-model="email"
                type="email"
                autocomplete="email"
                required
                autofocus
                class="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-accent-500 focus:outline-none"
              >
            </label>

            <label class="block">
              <span class="text-xs font-medium text-gray-700">Password</span>
              <input
                v-model="password"
                type="password"
                autocomplete="current-password"
                required
                class="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-accent-500 focus:outline-none"
              >
            </label>

            <p
              v-if="error"
              class="text-xs text-red-600"
              role="alert"
            >
              {{ error }}
            </p>

            <button
              type="submit"
              :disabled="submitting"
              class="w-full rounded bg-accent-500 text-white px-4 py-2 text-sm font-medium hover:bg-accent-600 transition-colors disabled:opacity-60"
            >
              {{ submitting ? 'Signing in…' : 'Sign in' }}
            </button>
          </form>
        </template>
      </div>
    </div>
  </div>
</template>
