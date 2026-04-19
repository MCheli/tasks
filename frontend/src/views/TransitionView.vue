<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useCyclesStore } from '@/stores/cycles'
import * as cyclesApi from '@/api/cycles'

const router = useRouter()
const cycles = useCyclesStore()
const submitting = ref(false)
const error = ref('')

// Map persistent_task_id → 'forward' | 'complete' | 'cancel'
const actions = reactive({})

onMounted(async () => {
  await cycles.refresh()
  for (const t of cycles.tasks.open) {
    actions[t.persistent_task_id] ??= 'forward'
  }
})

const summary = computed(() => {
  const out = { forward: 0, complete: 0, cancel: 0 }
  for (const v of Object.values(actions)) out[v] += 1
  return out
})

const ACTION_ORDER = ['forward', 'complete', 'cancel']
function cycleAction(pid) {
  const i = ACTION_ORDER.indexOf(actions[pid])
  actions[pid] = ACTION_ORDER[(i + 1) % ACTION_ORDER.length]
}

const ICONS = { forward: '→', complete: '✓', cancel: '✗' }
const COLORS = {
  forward: 'bg-accent-500 text-white',
  complete: 'bg-green-500 text-white',
  cancel: 'bg-gray-400 text-white',
}
const LABELS = { forward: 'Forward', complete: 'Complete', cancel: 'Cancel' }

async function startCycle() {
  if (submitting.value) return
  if (!cycles.currentCycle?.id) {
    error.value = 'No active cycle.'
    return
  }
  const msg =
    cycles.tasks.open.length === 0
      ? 'Start a new empty cycle?'
      : 'Start a new cycle? The current one will be closed.'
  if (!confirm(msg)) return

  submitting.value = true
  error.value = ''
  try {
    const payload = Object.entries(actions).map(([pid, action]) => ({
      persistent_task_id: pid,
      action,
    }))
    await cyclesApi.transitionCycle(cycles.currentCycle.id, payload)
    await cycles.refresh()
    router.replace('/cycle')
  } catch (e) {
    error.value = e?.response?.data?.detail || 'Failed to start new cycle'
  } finally {
    submitting.value = false
  }
}

function cancel() {
  router.replace('/cycle')
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <header class="sticky top-0 z-10 bg-white border-b border-gray-200">
      <div class="max-w-2xl mx-auto px-3 py-2 flex items-center justify-between gap-3">
        <button
          class="text-sm text-gray-500 hover:text-gray-700"
          @click="cancel"
        >
          ← Cancel
        </button>
        <h1 class="text-sm sm:text-base font-semibold capitalize">
          New Cycle Planning · {{ cycles.activeCategory }}
        </h1>
        <div class="w-16 sm:w-24" />
      </div>
      <div class="max-w-2xl mx-auto px-3 pb-2 text-xs sm:text-sm text-gray-600 flex items-center gap-3 flex-wrap">
        <span class="text-accent-600 font-medium">→ {{ summary.forward }} forwarding</span>
        <span class="text-green-600 font-medium">✓ {{ summary.complete }} completing</span>
        <span class="text-gray-500 font-medium">✗ {{ summary.cancel }} canceling</span>
      </div>
    </header>

    <main class="max-w-2xl mx-auto p-4 pb-32">
      <div
        v-if="!cycles.tasks.open.length"
        class="bg-white rounded-lg border border-gray-200 p-8 text-center text-sm text-gray-500"
      >
        No open tasks to triage. Ready to start a fresh cycle?
      </div>

      <div
        v-else
        class="bg-white rounded-lg border border-gray-200 overflow-hidden"
      >
        <div
          v-for="task in cycles.tasks.open"
          :key="task.id"
          class="flex items-start gap-3 px-3 py-2.5 border-b last:border-b-0 border-gray-100"
        >
          <button
            class="flex-shrink-0 w-9 h-9 rounded-md flex items-center justify-center font-bold transition-colors"
            :class="COLORS[actions[task.persistent_task_id] || 'forward']"
            :aria-label="`Action for task ${task.display_id}: ${LABELS[actions[task.persistent_task_id] || 'forward']}`"
            :title="LABELS[actions[task.persistent_task_id] || 'forward']"
            @click="cycleAction(task.persistent_task_id)"
          >
            {{ ICONS[actions[task.persistent_task_id] || 'forward'] }}
          </button>
          <div class="flex-1 min-w-0 pt-1">
            <div class="flex items-baseline gap-2">
              <span class="text-[11px] font-mono text-gray-400">#{{ task.display_id }}</span>
              <span class="text-sm break-words">{{ task.title }}</span>
            </div>
            <p
              v-if="task.notes"
              class="text-xs text-gray-500 mt-0.5 line-clamp-2 whitespace-pre-wrap"
            >
              {{ task.notes }}
            </p>
          </div>
        </div>
      </div>

      <p
        v-if="error"
        class="text-xs text-red-600 mt-3"
        role="alert"
      >
        {{ error }}
      </p>
    </main>

    <!-- Start button -->
    <div class="fixed bottom-0 left-0 right-0 sm:bottom-6 sm:right-6 sm:left-auto safe-bottom">
      <div class="sm:hidden bg-gradient-to-t from-gray-50 via-gray-50/90 to-transparent pt-6 px-4 pb-4">
        <button
          class="w-full bg-accent-500 text-white px-6 py-3 rounded-lg shadow-md font-medium hover:bg-accent-600 disabled:opacity-50"
          :disabled="submitting"
          @click="startCycle"
        >
          {{ submitting ? 'Starting…' : 'Start New Cycle' }}
        </button>
      </div>
      <button
        class="hidden sm:block bg-accent-500 text-white px-6 py-3 rounded-full shadow-lg font-medium hover:bg-accent-600 disabled:opacity-50"
        :disabled="submitting"
        @click="startCycle"
      >
        {{ submitting ? 'Starting…' : 'Start New Cycle' }}
      </button>
    </div>
  </div>
</template>
