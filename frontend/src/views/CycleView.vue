<!-- Phase 1 placeholder; full task list lands in Phase 4. -->
<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

async function logout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <header class="bg-white border-b border-gray-200">
      <div class="max-w-2xl mx-auto flex items-center justify-between p-3">
        <h1 class="text-lg font-semibold">Tasks</h1>
        <div class="flex items-center gap-3">
          <span v-if="auth.user" class="text-xs text-gray-500">{{ auth.user.email }}</span>
          <button @click="logout" class="text-xs text-gray-500 hover:text-gray-700">
            Sign out
          </button>
        </div>
      </div>
    </header>
    <main class="max-w-2xl mx-auto p-6">
      <p class="text-sm text-gray-500">
        Authenticated. Cycle view UI coming in Phase 4.
      </p>
    </main>
  </div>
</template>
