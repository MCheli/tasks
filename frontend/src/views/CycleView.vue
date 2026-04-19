<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useCyclesStore } from '@/stores/cycles'
import * as tasksApi from '@/api/tasks'
import draggable from 'vuedraggable'

import TabSwitcher from '@/components/TabSwitcher.vue'
import TaskInput from '@/components/TaskInput.vue'
import TaskItem from '@/components/TaskItem.vue'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'

const router = useRouter()
const auth = useAuthStore()
const cycles = useCyclesStore()
const taskInputRef = ref(null)

onMounted(() => cycles.refresh())

useKeyboardShortcuts({
  n: () => taskInputRef.value?.focus(),
  'g h': () => router.push('/history'),
  'g c': () => router.push('/cycle'),
})

async function logout() {
  await auth.logout()
  router.replace('/login')
}

async function onReorderEnd(evt) {
  if (evt.oldIndex === evt.newIndex) return
  // The store's open list is already mutated by vuedraggable (it binds v-model).
  // Send the new position for the moved task to the server, then replace state
  // with the server's authoritative ordering.
  const moved = cycles.tasks.open[evt.newIndex]
  if (!moved) return
  try {
    const { data } = await tasksApi.reorderTask(moved.id, evt.newIndex)
    cycles.replaceOpen(data.tasks)
  } catch (e) {
    cycles.error = e?.response?.data?.detail || 'Failed to reorder'
    // Re-fetch to recover from any optimistic divergence.
    cycles.refresh()
  }
}

const cycleStartedRel = computed(() => {
  if (!cycles.currentCycle?.started_at) return ''
  const ms = Date.now() - new Date(cycles.currentCycle.started_at).getTime()
  const sec = Math.floor(ms / 1000)
  const min = Math.floor(sec / 60)
  const hr = Math.floor(min / 60)
  const day = Math.floor(hr / 24)
  if (day >= 1) return day === 1 ? '1 day ago' : `${day} days ago`
  if (hr >= 1) return hr === 1 ? '1 hour ago' : `${hr} hours ago`
  if (min >= 1) return min === 1 ? '1 minute ago' : `${min} minutes ago`
  return 'just now'
})
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <header class="sticky top-0 z-10 bg-white border-b border-gray-200">
      <div class="max-w-2xl mx-auto flex items-center justify-between gap-3 px-3 py-2">
        <h1 class="text-base font-semibold">Tasks</h1>
        <TabSwitcher class="hidden sm:flex" />
        <div class="flex items-center gap-1">
          <button
            class="p-2 text-gray-500 hover:text-gray-700 rounded"
            title="History"
            aria-label="History"
            @click="router.push('/history')"
          >
            <span aria-hidden="true">🕐</span>
          </button>
          <button
            class="p-2 text-gray-500 hover:text-gray-700 rounded text-xs"
            title="Sign out"
            aria-label="Sign out"
            @click="logout"
          >
            ↩︎
          </button>
        </div>
      </div>
      <!-- Mobile tab switcher row -->
      <div class="sm:hidden border-t border-gray-100 px-3 py-2">
        <TabSwitcher />
      </div>
    </header>

    <main class="max-w-2xl mx-auto p-4 pb-32">
      <!-- Meta line -->
      <div class="flex items-baseline justify-between text-xs text-gray-500 mb-3">
        <span>Cycle started {{ cycleStartedRel }}</span>
        <button
          class="hover:text-gray-700"
          :title="cycles.showResolved ? 'Hide done/canceled' : 'Show done/canceled'"
          @click="cycles.toggleShowResolved"
        >
          <span class="font-medium">{{ cycles.summary.open }}</span> open ·
          <span class="font-medium">{{ cycles.summary.completed }}</span> done ·
          <span class="font-medium">{{ cycles.summary.canceled }}</span> canceled
        </button>
      </div>

      <TaskInput ref="taskInputRef" class="mb-4" />

      <!-- Initial loading skeleton -->
      <div
        v-if="cycles.loading && !cycles.tasks.open.length && !cycles.tasks.completed.length"
        class="bg-white rounded-lg border border-gray-200 overflow-hidden"
      >
        <div
          v-for="i in 3"
          :key="i"
          class="flex items-center gap-3 px-3 py-3 border-b last:border-b-0 border-gray-100 animate-pulse"
        >
          <div class="w-5 h-5 rounded bg-gray-200"></div>
          <div class="h-3 bg-gray-200 rounded flex-1"></div>
        </div>
      </div>

      <!-- Open tasks (drag-reorderable) -->
      <section
        v-else-if="cycles.tasks.open.length"
        class="bg-white rounded-lg border border-gray-200 overflow-hidden"
      >
        <draggable
          v-model="cycles.tasks.open"
          item-key="id"
          handle=".drag-handle"
          ghost-class="bg-accent-50"
          drag-class="opacity-90"
          :animation="150"
          @end="onReorderEnd"
        >
          <template #item="{ element }">
            <TaskItem :task="element" />
          </template>
        </draggable>
      </section>
      <div
        v-else
        class="bg-white rounded-lg border border-gray-200 px-4 py-8 text-center text-sm text-gray-400"
      >
        No open tasks. Add one above — or press
        <kbd class="px-1.5 py-0.5 bg-gray-100 rounded text-[10px] font-mono">N</kbd>
        to focus the input.
      </div>

      <!-- Completed -->
      <section
        v-if="cycles.showResolved && cycles.tasks.completed.length"
        class="mt-6"
      >
        <h2 class="text-[11px] uppercase tracking-wide font-medium text-gray-500 mb-1 px-1">
          Completed ({{ cycles.tasks.completed.length }})
        </h2>
        <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <TaskItem
            v-for="t in cycles.tasks.completed"
            :key="t.id"
            :task="t"
          />
        </div>
      </section>

      <!-- Canceled -->
      <section
        v-if="cycles.showResolved && cycles.tasks.canceled.length"
        class="mt-6"
      >
        <h2 class="text-[11px] uppercase tracking-wide font-medium text-gray-500 mb-1 px-1">
          Canceled ({{ cycles.tasks.canceled.length }})
        </h2>
        <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <TaskItem
            v-for="t in cycles.tasks.canceled"
            :key="t.id"
            :task="t"
          />
        </div>
      </section>

      <p
        v-if="cycles.error"
        class="text-xs text-red-600 mt-4"
        role="alert"
      >{{ cycles.error }}</p>
    </main>

    <!-- Start New Cycle button -->
    <div class="fixed bottom-0 left-0 right-0 sm:bottom-6 sm:right-6 sm:left-auto safe-bottom">
      <div class="sm:hidden bg-gradient-to-t from-gray-50 via-gray-50/90 to-transparent pt-6 px-4 pb-4">
        <button
          class="w-full bg-accent-500 text-white px-6 py-3 rounded-lg shadow-md font-medium hover:bg-accent-600"
          @click="router.push('/cycle/transition')"
        >
          Start New Cycle
        </button>
      </div>
      <button
        class="hidden sm:block bg-accent-500 text-white px-5 py-2.5 rounded-full shadow-lg font-medium hover:bg-accent-600"
        @click="router.push('/cycle/transition')"
      >
        Start New Cycle
      </button>
    </div>
  </div>
</template>
