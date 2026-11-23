<script setup>
import { computed, ref, watch } from 'vue'
import * as tasksApi from '@/api/tasks'
import { useCyclesStore } from '@/stores/cycles'
import { fmtDateTime, relativeTime } from '@/composables/relativeTime'

const props = defineProps({
  task: { type: Object, required: true },
  readonly: { type: Boolean, default: false },
})

const cycles = useCyclesStore()
const expanded = ref(false)
const log = ref(null) // notes log, loaded on expand
const logLoading = ref(false)
const noteText = ref('')
const addingNote = ref(false)
const busy = ref(false)

const STATUS_LABELS = {
  open: 'Open',
  in_progress: 'In progress',
  blocked: 'Blocked',
  done: 'Done',
  canceled: 'Canceled',
}
const CHIP = {
  open: 'bg-gray-100 text-gray-700',
  in_progress: 'bg-blue-100 text-blue-800',
  blocked: 'bg-amber-100 text-amber-800',
  done: 'bg-green-100 text-green-800',
  canceled: 'bg-gray-200 text-gray-500',
}
const SETTABLE = ['open', 'in_progress', 'blocked', 'done']

/** The status shown: canceled wins, then the agent status (done for completed). */
const shownStatus = computed(() => {
  if (props.task.status === 'canceled') return 'canceled'
  if (props.task.status === 'completed') return 'done'
  return props.task.agent_status || 'open'
})
const isResolved = computed(() => props.task.status !== 'open')
const linkLabel = computed(() => {
  if (!props.task.link) return ''
  try {
    const u = new URL(props.task.link)
    return (u.host + u.pathname).replace(/\/$/, '')
  } catch {
    return props.task.link
  }
})

async function loadLog() {
  logLoading.value = true
  try {
    const { data } = await tasksApi.getTask(props.task.id)
    log.value = data.notes_log || []
  } catch (e) {
    cycles.error = e?.response?.data?.detail || 'Failed to load notes'
  } finally {
    logLoading.value = false
  }
}

function toggle() {
  expanded.value = !expanded.value
  if (expanded.value && log.value === null) loadLog()
}

watch(
  () => props.task.note_count,
  (n, old) => {
    if (expanded.value && n !== old) loadLog()
  }
)

async function setStatus(status) {
  if (props.readonly || busy.value || status === shownStatus.value) return
  busy.value = true
  try {
    const { data } = await tasksApi.updateTask(props.task.id, { agent_status: status })
    cycles.replaceTask(data.task)
  } catch (e) {
    cycles.error = e?.response?.data?.detail || 'Failed to update status'
  } finally {
    busy.value = false
  }
}

async function toggleDone() {
  await setStatus(isResolved.value ? 'open' : 'done')
}

async function submitNote() {
  const body = noteText.value.trim()
  if (!body || addingNote.value || props.readonly) return
  addingNote.value = true
  try {
    const { data } = await tasksApi.addNote(props.task.id, body)
    noteText.value = ''
    log.value = [...(log.value || []), data.note]
    cycles.replaceTask(data.task)
  } catch (e) {
    cycles.error = e?.response?.data?.detail || 'Failed to add note'
  } finally {
    addingNote.value = false
  }
}

async function deleteTask() {
  if (props.readonly) return
  if (!confirm('Delete this agent item and its notes log? This cannot be undone.')) return
  try {
    await tasksApi.deleteTask(props.task.id)
    cycles.removeTask(props.task.id)
  } catch (e) {
    cycles.error = e?.response?.data?.detail || 'Failed to delete task'
  }
}
</script>

<template>
  <div
    class="group relative flex items-start gap-3 px-3 py-2.5 bg-white border-b border-gray-100"
    :class="{ 'opacity-70': task.status === 'completed', 'opacity-50': task.status === 'canceled' }"
    data-testid="agent-task"
  >
    <!-- Done toggle -->
    <button
      v-demo-lock
      class="mt-0.5 flex-shrink-0 w-5 h-5 rounded flex items-center justify-center text-xs"
      :class="{
        'bg-green-500 text-white': task.status === 'completed',
        'bg-gray-300 text-white': task.status === 'canceled',
        'border-2 border-gray-300 hover:border-accent-500': task.status === 'open',
      }"
      :disabled="readonly || busy"
      :aria-label="isResolved ? 'Reopen' : 'Mark done'"
      @click.stop="toggleDone"
    >
      <span v-if="task.status === 'completed'">✓</span>
      <span v-else-if="task.status === 'canceled'">✗</span>
    </button>

    <div
      class="flex-1 min-w-0 cursor-pointer"
      @click="toggle"
    >
      <!-- Title row -->
      <div class="flex items-start gap-2">
        <span class="text-[11px] font-mono text-gray-400 pt-0.5">#{{ task.display_id }}</span>
        <span
          class="text-sm break-words flex-1"
          :class="{ 'line-through': task.status !== 'open' }"
        >{{ task.title }}</span>
        <span
          class="flex-shrink-0 text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded-full"
          :class="CHIP[shownStatus]"
          data-testid="status-chip"
        >{{ STATUS_LABELS[shownStatus] }}</span>
      </div>
      <!-- Meta line -->
      <div class="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-gray-400">
        <span
          v-if="task.source"
          class="truncate max-w-[12rem]"
          :title="task.source"
        >{{
          task.source
        }}</span>
        <span v-if="task.source">·</span>
        <span :title="new Date(task.updated_at).toLocaleString()">updated {{ relativeTime(task.updated_at) }}</span>
        <span v-if="task.note_count">· {{ task.note_count }} {{ task.note_count === 1 ? 'note' : 'notes' }}</span>
        <a
          v-if="task.link"
          :href="task.link"
          target="_blank"
          rel="noopener noreferrer"
          class="text-accent-600 hover:underline truncate max-w-[14rem]"
          :title="task.link"
          @click.stop
        >↗ {{ linkLabel }}</a>
      </div>

      <!-- Expanded body -->
      <div
        v-if="expanded"
        class="mt-3 space-y-3"
        @click.stop
      >
        <p
          v-if="task.notes"
          class="text-sm text-gray-600 whitespace-pre-wrap"
        >
          {{ task.notes }}
        </p>

        <!-- Status control -->
        <div
          v-if="!readonly && task.status !== 'canceled'"
          role="radiogroup"
          aria-label="Status"
          class="inline-flex flex-wrap bg-gray-100 rounded-lg p-0.5 text-xs"
        >
          <button
            v-for="s in SETTABLE"
            :key="s"
            v-demo-lock
            role="radio"
            :aria-checked="shownStatus === s"
            class="px-2.5 py-1 rounded-md font-medium transition-colors"
            :class="
              shownStatus === s
                ? 'bg-white shadow-sm text-gray-900'
                : 'text-gray-500 hover:text-gray-700'
            "
            :disabled="busy"
            @click="setStatus(s)"
          >
            {{ STATUS_LABELS[s] }}
          </button>
        </div>
        <button
          v-else-if="!readonly"
          v-demo-lock
          class="text-xs px-2 py-1 text-gray-500 hover:bg-gray-100 rounded"
          @click="setStatus('open')"
        >
          Reopen
        </button>

        <!-- Notes log -->
        <div>
          <h3 class="text-[11px] uppercase tracking-wide font-medium text-gray-500 mb-1">
            Notes log
          </h3>
          <p
            v-if="logLoading && log === null"
            class="text-xs text-gray-400"
          >
            Loading…
          </p>
          <p
            v-else-if="!log || !log.length"
            class="text-xs text-gray-400 italic"
          >
            No notes yet.
          </p>
          <ol
            v-else
            class="space-y-1.5"
            data-testid="notes-log"
          >
            <li
              v-for="n in log"
              :key="n.id"
              class="text-sm"
            >
              <div class="text-[11px] text-gray-400">
                <span class="font-medium text-gray-500">{{ n.author }}</span>
                · {{ fmtDateTime(n.created_at) }}
              </div>
              <div class="text-gray-700 whitespace-pre-wrap">
                {{ n.body }}
              </div>
            </li>
          </ol>
          <form
            v-if="!readonly"
            class="mt-2 flex items-start gap-2"
            @submit.prevent="submitNote"
          >
            <textarea
              v-model="noteText"
              v-demo-lock
              rows="2"
              maxlength="20000"
              placeholder="Add a note…"
              class="flex-1 text-sm border border-gray-200 rounded px-2 py-1 resize-none focus:outline-none focus:border-accent-500"
              @keydown.enter.meta.prevent="submitNote"
              @keydown.enter.ctrl.prevent="submitNote"
            />
            <button
              v-demo-lock
              type="submit"
              class="text-xs px-3 py-1.5 rounded bg-accent-500 text-white font-medium hover:bg-accent-600 disabled:opacity-50"
              :disabled="!noteText.trim() || addingNote"
            >
              {{ addingNote ? 'Adding…' : 'Add note' }}
            </button>
          </form>
        </div>

        <div class="text-[11px] text-gray-400 flex flex-wrap gap-x-3">
          <span>Created {{ fmtDateTime(task.created_at) }}</span>
          <span v-if="task.push_forward_count > 0">Carried over {{ task.push_forward_count }}×</span>
          <span v-if="task.completed_at">Done {{ fmtDateTime(task.completed_at) }}</span>
          <button
            v-if="!readonly"
            v-demo-lock
            class="ml-auto text-gray-500 hover:text-red-600"
            @click="deleteTask"
          >
            Delete…
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
