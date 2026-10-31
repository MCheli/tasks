<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppConfigStore } from '@/stores/appConfig'
import HeroVisual from '@/components/login/HeroVisual.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const appConfig = useAppConfigStore()

const email = ref('')
const password = ref('')
const submitting = ref(false)
const error = ref('')

const ready = computed(() => appConfig.loaded)

const features = [
  'Personal + Professional',
  'End-of-cycle triage',
  'Task history timeline',
  'Keyboard shortcuts',
  'API keys',
]

onMounted(async () => {
  if (!auth.initialized) await auth.init()
  if (auth.user) {
    router.replace(route.query.next || '/cycle')
    return
  }
  await appConfig.load()
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

async function enterDemo() {
  if (submitting.value) return
  error.value = ''
  submitting.value = true
  try {
    await auth.demoLogin()
    router.replace('/cycle')
  } catch (e) {
    error.value = e.response?.data?.detail || 'The demo could not be opened. Try again in a minute.'
  } finally {
    submitting.value = false
  }
}

function googleLogin() {
  window.location.href = '/api/auth/google/login'
}
</script>

<template>
  <div class="min-h-dvh grid lg:grid-cols-[minmax(0,1.25fr)_minmax(24rem,1fr)] bg-white dark:bg-gray-950">
    <!-- Hero: always dark, the app at a glance -->
    <section class="hero relative overflow-hidden text-white px-6 sm:px-10 lg:px-14 pt-7 pb-8 lg:py-12 flex flex-col">
      <div class="relative z-10 flex items-center gap-2.5">
        <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/20 text-lg font-bold">✓</span>
        <span class="text-xl font-bold tracking-tight">Tasks</span>
      </div>

      <div class="relative z-10 flex-1 flex flex-col justify-center gap-8 lg:gap-10 mt-6 sm:mt-8 lg:mt-12 max-w-2xl">
        <div>
          <h1 class="text-[1.75rem] sm:text-4xl lg:text-[2.75rem] font-semibold leading-[1.12] tracking-tight [text-wrap:balance]">
            Plan in cycles. Carry forward what matters. Let go of the rest.
          </h1>
          <p class="mt-3 sm:mt-4 text-[15px] sm:text-lg text-indigo-100/80 max-w-xl leading-relaxed">
            A self-hosted todo app with separate Personal and Professional lists. Each cycle ends
            with a quick triage, every task keeps its history, and API keys let your own scripts in.
          </p>
        </div>

        <HeroVisual class="hidden sm:block" />

        <ul class="hidden sm:flex flex-wrap gap-2">
          <li
            v-for="f in features"
            :key="f"
            class="rounded-full bg-white/[0.08] ring-1 ring-white/15 px-3 py-1 text-xs sm:text-sm text-indigo-50"
          >
            {{ f }}
          </li>
        </ul>
      </div>
    </section>

    <!-- Sign in -->
    <section class="flex flex-col justify-center px-6 sm:px-10 py-8 sm:py-12 lg:py-14 safe-bottom">
      <div class="w-full max-w-sm mx-auto">
        <div
          v-if="!ready"
          class="h-36 rounded-xl bg-gray-100 dark:bg-gray-800 animate-pulse"
        />

        <!-- The public demo deployment -->
        <template v-else-if="appConfig.demo">
          <span class="inline-flex items-center rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 px-2.5 py-0.5 text-xs font-medium">Live demo</span>
          <h2 class="mt-3 text-2xl font-semibold text-gray-900 dark:text-white">
            Look around Tasks
          </h2>
          <p class="mt-2 text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
            You'll see the task lists of
            <strong class="text-gray-800 dark:text-gray-200">Claudius Banks</strong>, a made-up
            software engineer, the same person as in the
            <a
              href="https://money-demo.markcheli.com"
              class="text-accent-600 dark:text-accent-400 underline underline-offset-2"
            >Tallied demo</a>.
            Every task and cycle is generated and rebuilt each night. Every page works; nothing can
            be changed.
          </p>
          <button
            type="button"
            data-testid="enter-demo"
            :disabled="submitting"
            class="mt-6 w-full inline-flex items-center justify-center gap-2 py-3 rounded-lg bg-accent-600 text-white text-sm font-semibold hover:bg-accent-700 disabled:opacity-50 transition-colors"
            @click="enterDemo"
          >
            {{ submitting ? 'Opening…' : 'Enter the demo' }} <span aria-hidden="true">→</span>
          </button>
          <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">
            No sign-up, no email, nothing to install.
          </p>
          <p
            v-if="error"
            role="alert"
            class="mt-4 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 rounded-lg px-3 py-2"
          >
            {{ error }}
          </p>
        </template>

        <template v-else>
          <h2 class="text-2xl font-semibold text-gray-900 dark:text-white">
            Sign in
          </h2>
          <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Pick up where your cycle left off.
          </p>

          <!-- Google SSO is the only path when configured. -->
          <button
            v-if="appConfig.googleConfigured"
            type="button"
            class="mt-6 w-full inline-flex items-center justify-center gap-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
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

          <!-- Fallback: password form when Google isn't configured. -->
          <form
            v-else
            class="mt-6 space-y-3"
            @submit.prevent="submit"
          >
            <label class="block">
              <span class="text-xs font-medium text-gray-700 dark:text-gray-300">Email</span>
              <input
                v-model="email"
                type="email"
                autocomplete="email"
                required
                class="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none"
              >
            </label>

            <label class="block">
              <span class="text-xs font-medium text-gray-700 dark:text-gray-300">Password</span>
              <input
                v-model="password"
                type="password"
                autocomplete="current-password"
                required
                class="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none"
              >
            </label>

            <p
              v-if="error"
              class="text-xs text-red-600 dark:text-red-400"
              role="alert"
            >
              {{ error }}
            </p>

            <button
              type="submit"
              :disabled="submitting"
              class="w-full rounded-lg bg-accent-500 text-white px-4 py-2.5 text-sm font-medium hover:bg-accent-600 transition-colors disabled:opacity-60"
            >
              {{ submitting ? 'Signing in…' : 'Sign in' }}
            </button>
          </form>

          <a
            v-if="appConfig.demoUrl"
            :href="appConfig.demoUrl"
            data-testid="demo-link"
            class="group mt-8 block rounded-xl border border-accent-100 dark:border-accent-700/50 bg-accent-50/60 dark:bg-accent-700/10 p-4 hover:border-accent-200 dark:hover:border-accent-500 transition-colors"
          >
            <div class="flex items-center justify-between gap-3">
              <span class="text-sm font-semibold text-gray-900 dark:text-white">Just looking? Try the live demo</span>
              <span
                aria-hidden="true"
                class="text-accent-600 dark:text-accent-400 transition-transform group-hover:translate-x-0.5"
              >→</span>
            </div>
            <p class="mt-1 text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
              Every page, filled with the task lists of Claudius Banks, a made-up software engineer.
              Read-only, no sign-in.
            </p>
          </a>
        </template>

        <p class="mt-10 text-xs text-gray-400 dark:text-gray-500">
          Built by
          <a
            href="https://www.markcheli.com"
            class="underline underline-offset-2 hover:text-gray-600 dark:hover:text-gray-300"
          >Mark Cheli</a>
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.hero {
  background:
    radial-gradient(55rem 28rem at 85% 0%, rgba(99, 102, 241, 0.38), transparent 60%),
    radial-gradient(40rem 26rem at 0% 100%, rgba(16, 185, 129, 0.16), transparent 60%),
    linear-gradient(165deg, #0c1024 0%, #12173a 55%, #0e1430 100%);
}
/* Faint cycle bands, like the history timeline's. */
.hero::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image: repeating-linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.035) 0 88px,
    transparent 88px 176px
  );
  mask-image: radial-gradient(ellipse at 60% 40%, black 30%, transparent 75%);
}
</style>
