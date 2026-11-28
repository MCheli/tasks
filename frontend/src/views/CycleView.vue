<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useCyclesStore } from '@/stores/cycles'
import { useAppConfigStore } from '@/stores/appConfig'
import * as tasksApi from '@/api/tasks'
import draggable from 'vuedraggable'

import TabSwitcher from '@/components/TabSwitcher.vue'
import OwnerSwitcher from '@/components/OwnerSwitcher.vue'
import TaskInput from '@/components/TaskInput.vue'
import TaskItem from '@/components/TaskItem.vue'
import AgentTaskItem from '@/components/AgentTaskItem.vue'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'

const router = useRouter()
const auth = useAuthStore()
const cycles = useCyclesStore()
const appConfig = useAppConfigStore()
const taskInputRef = ref(null)

onMounted(() => cycles.refresh())

useKeyboardShortcuts({
  n: () => taskInputRef.value?.focus(),
  'g h': () => router.push('/history'),
  'g c': () => router.push('/cycle'),
  'g s': () => router.push('/settings'),
  'g a': () => cycles.setOwner('agent'),
  'g m': () => cycles.setOwner('human'),
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

const isAgents = computed(() => cycles.activeOwner === 'agent')
const shown = computed(() => cycles.visibleTasks)
const summary = computed(() => cycles.visibleSummary)
const initialLoading = computed(
  () => cycles.loading && !shown.value.open.length && !shown.value.completed.length
)

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
  <div class="min-h-dvh bg-gray-50">
    <header class="sticky top-0 z-10 bg-white border-b border-gray-200">
      <div class="max-w-2xl mx-auto flex items-center justify-between gap-3 px-3 py-1">
        <h1 class="text-base font-semibold">
          Tasks
        </h1>
        <TabSwitcher class="hidden sm:flex" />
        <div class="flex items-center gap-1">
          <button
            class="w-11 h-11 flex items-center justify-center text-base text-gray-500 hover:text-gray-700 rounded-sm"
            title="History"
            aria-label="History"
            @click="router.push('/history')"
          >
            <span aria-hidden="true">🕐</span>
          </button>
          <button
            class="w-11 h-11 flex items-center justify-center text-base text-gray-500 hover:text-gray-700 rounded-sm"
            title="Settings"
            aria-label="Settings"
            @click="router.push('/settings')"
          >
            <span aria-hidden="true">⚙︎</span>
          </button>
          <button
            class="w-11 h-11 flex items-center justify-center text-base text-gray-500 hover:text-gray-700 rounded-sm"
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

    <main class="max-w-2xl mx-auto p-4 pb-[calc(1.5rem+env(safe-area-inset-bottom))] sm:pb-32">
      <!-- Mine / Agents + meta line -->
      <div class="flex items-center justify-between gap-3 mb-3">
        <OwnerSwitcher />
        <button
          class="text-xs text-gray-500 hover:text-gray-700 text-right touch:min-h-11"
          :title="cycles.showResolved ? 'Hide done/canceled' : 'Show done/canceled'"
          @click="cycles.toggleShowResolved"
        >
          <span class="font-medium">{{ summary.open }}</span> open ·
          <span class="font-medium">{{ summary.completed }}</span> done
          <template v-if="!isAgents">
            · <span class="font-medium">{{ summary.canceled }}</span> canceled
          </template>
          <template v-else-if="summary.blocked">
            · <span class="font-medium text-amber-700">{{ summary.blocked }}</span> blocked
          </template>
        </button>
      </div>
      <p class="text-[11px] text-gray-400 mb-3">
        Cycle started {{ cycleStartedRel }}
        <template v-if="isAgents">
          · the agents' follow-up list for this cycle; open items carry over on their own
        </template>
      </p>

      <TaskInput
        ref="taskInputRef"
        class="mb-4"
      />

      <!-- Initial loading skeleton -->
      <div
        v-if="initialLoading"
        class="bg-white rounded-lg border border-gray-200 overflow-hidden"
      >
        <div
          v-for="i in 3"
          :key="i"
          class="flex items-center gap-3 px-3 py-3 border-b last:border-b-0 border-gray-100 animate-pulse"
        >
          <div class="w-5 h-5 rounded-sm bg-gray-200" />
          <div class="h-3 bg-gray-200 rounded-sm flex-1" />
        </div>
      </div>

      <!-- ── Mark's list: open tasks (drag-reorderable) ── -->
      <template v-else-if="!isAgents">
        <section
          v-if="cycles.tasks.open.length"
          class="bg-white rounded-lg border border-gray-200 overflow-hidden"
        >
          <draggable
            v-model="cycles.tasks.open"
            item-key="id"
            handle=".drag-handle"
            :disabled="appConfig.demo"
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
          No open tasks. Add one above<span class="kbd-hint">
            — or press
            <kbd class="px-1.5 py-0.5 bg-gray-100 rounded-sm text-[10px] font-mono">N</kbd>
            to focus the input</span>.
        </div>
      </template>

      <!-- ── Agents' list: open items with status chips ── -->
      <template v-else>
        <section
          v-if="cycles.agentTasks.open.length"
          class="bg-white rounded-lg border border-gray-200 overflow-hidden"
          data-testid="agent-open-list"
        >
          <AgentTaskItem
            v-for="t in cycles.agentTasks.open"
            :key="t.id"
            :task="t"
          />
        </section>
        <div
          v-else
          class="bg-white rounded-lg border border-gray-200 px-4 py-8 text-center text-sm text-gray-400"
        >
          Nothing open on the agents' list. Claude adds items here through the connector when it
          has follow-up work to track.
        </div>
      </template>

      <!-- Completed / Done -->
      <section
        v-if="cycles.showResolved && shown.completed.length"
        class="mt-6"
      >
        <h2 class="text-[11px] uppercase tracking-wide font-medium text-gray-500 mb-1 px-1">
          {{ isAgents ? 'Done' : 'Completed' }} ({{ shown.completed.length }})
        </h2>
        <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <template v-if="isAgents">
            <AgentTaskItem
              v-for="t in shown.completed"
              :key="t.id"
              :task="t"
            />
          </template>
          <template v-else>
            <TaskItem
              v-for="t in shown.completed"
              :key="t.id"
              :task="t"
            />
          </template>
        </div>
      </section>

      <!-- Canceled -->
      <section
        v-if="cycles.showResolved && shown.canceled.length"
        class="mt-6"
      >
        <h2 class="text-[11px] uppercase tracking-wide font-medium text-gray-500 mb-1 px-1">
          Canceled ({{ shown.canceled.length }})
        </h2>
        <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <template v-if="isAgents">
            <AgentTaskItem
              v-for="t in shown.canceled"
              :key="t.id"
              :task="t"
            />
          </template>
          <template v-else>
            <TaskItem
              v-for="t in shown.canceled"
              :key="t.id"
              :task="t"
            />
          </template>
        </div>
      </section>

      <p
        v-if="cycles.error"
        class="text-xs text-red-600 mt-4"
        role="alert"
      >
        {{ cycles.error }}
      </p>

      <!-- Phones: Start New Cycle sits after the list, so it never covers a task. -->
      <button
        class="sm:hidden mt-8 w-full bg-accent-500 text-white px-6 py-3 rounded-lg shadow-md font-medium hover:bg-accent-600"
        @click="router.push('/cycle/transition')"
      >
        Start New Cycle
      </button>
    </main>

    <!-- Wider screens: a floating Start New Cycle button -->
    <button
      class="hidden sm:block fixed bottom-6 right-6 bg-accent-500 text-white px-5 py-2.5 rounded-full shadow-lg font-medium hover:bg-accent-600"
      @click="router.push('/cycle/transition')"
    >
      Start New Cycle
    </button>
  </div>
</template>
