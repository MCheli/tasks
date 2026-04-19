<script setup>
import { ref, watch } from 'vue'
import * as tasksApi from '@/api/tasks'
import { useCyclesStore } from '@/stores/cycles'

const props = defineProps({
  task: { type: Object, required: true },
  readonly: { type: Boolean, default: false },
})

const cycles = useCyclesStore()
const expanded = ref(false)
const editing = ref(false)
const menuOpen = ref(false)

const editTitle = ref(props.task.title)
const editNotes = ref(props.task.notes || '')

watch(
  () => props.task,
  (t) => {
    editTitle.value = t.title
    editNotes.value = t.notes || ''
  }
)

async function toggleComplete() {
  if (props.readonly) return
  const newStatus = props.task.status === 'completed' ? 'open' : 'completed'
  try {
    const { data } = await tasksApi.updateTask(props.task.id, { status: newStatus })
    cycles.replaceTask(data.task)
  } catch (e) {
    cycles.error = e?.response?.data?.detail || 'Failed to update task'
  }
}

async function cancelTask() {
  if (props.readonly) return
  try {
    const { data } = await tasksApi.updateTask(props.task.id, { status: 'canceled' })
    cycles.replaceTask(data.task)
    menuOpen.value = false
  } catch (e) {
    cycles.error = e?.response?.data?.detail || 'Failed to cancel task'
  }
}

async function reopenTask() {
  if (props.readonly) return
  try {
    const { data } = await tasksApi.updateTask(props.task.id, { status: 'open' })
    cycles.replaceTask(data.task)
  } catch (e) {
    cycles.error = e?.response?.data?.detail || 'Failed to reopen task'
  }
}

async function deleteTask() {
  if (props.readonly) return
  if (!confirm('Delete this task and all its history? This cannot be undone.'))
    return
  try {
    await tasksApi.deleteTask(props.task.id)
    cycles.removeTask(props.task.id)
  } catch (e) {
    cycles.error = e?.response?.data?.detail || 'Failed to delete task'
  }
}

async function saveEdit() {
  if (props.readonly) return
  try {
    const { data } = await tasksApi.updateTask(props.task.id, {
      title: editTitle.value.trim(),
      notes: editNotes.value.trim() || null,
    })
    cycles.replaceTask(data.task)
    editing.value = false
  } catch (e) {
    cycles.error = e?.response?.data?.detail || 'Failed to save task'
  }
}

function startEdit() {
  if (props.readonly) return
  editing.value = true
  expanded.value = true
}

function cancelEdit() {
  editTitle.value = props.task.title
  editNotes.value = props.task.notes || ''
  editing.value = false
}

function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}
</script>

<template>
  <div
    class="group relative flex items-start gap-3 px-3 py-2.5 bg-white border-b border-gray-100"
    :class="{
      'opacity-70': task.status === 'completed',
      'opacity-50': task.status === 'canceled',
    }"
  >
    <!-- Drag handle (desktop hover only, ignored when not 'open') -->
    <span
      v-if="task.status === 'open' && !readonly"
      class="drag-handle hidden group-hover:block absolute left-0 top-1/2 -translate-y-1/2 -ml-4 cursor-grab text-gray-300"
      title="Drag to reorder"
      aria-hidden="true"
    >⋮⋮</span>

    <!-- Status icon / checkbox -->
    <button
      class="mt-0.5 flex-shrink-0 w-5 h-5 rounded flex items-center justify-center text-xs"
      :class="{
        'bg-green-500 text-white': task.status === 'completed',
        'bg-gray-300 text-white': task.status === 'canceled',
        'border-2 border-gray-300 hover:border-accent-500':
          task.status === 'open',
      }"
      :disabled="readonly"
      :aria-label="
        task.status === 'completed' ? 'Mark incomplete' : 'Mark complete'
      "
      @click.stop="toggleComplete"
    >
      <span v-if="task.status === 'completed'">✓</span>
      <span v-else-if="task.status === 'canceled'">✗</span>
    </button>

    <!-- Title + expand -->
    <div class="flex-1 min-w-0 cursor-pointer" @click="expanded = !expanded">
      <div class="flex items-baseline gap-2">
        <span class="text-[11px] font-mono text-gray-400">#{{ task.display_id }}</span>
        <span
          class="text-sm break-words"
          :class="{ 'line-through': task.status !== 'open' }"
        >{{ task.title }}</span>
      </div>

      <!-- Expanded body -->
      <div v-if="expanded" class="mt-2 space-y-2" @click.stop>
        <template v-if="!editing">
          <p
            v-if="task.notes"
            class="text-sm text-gray-600 whitespace-pre-wrap"
          >{{ task.notes }}</p>
          <p
            v-else
            class="text-xs text-gray-400 italic"
          >No notes.</p>
          <div class="text-[11px] text-gray-400 flex flex-wrap gap-x-3">
            <span>Created {{ fmtDate(task.created_at) }}</span>
            <span v-if="task.push_forward_count > 0">
              Pushed forward {{ task.push_forward_count }}×
            </span>
            <span v-if="task.completed_at">
              Completed {{ fmtDate(task.completed_at) }}
            </span>
            <span v-if="task.canceled_at">
              Canceled {{ fmtDate(task.canceled_at) }}
            </span>
          </div>
        </template>
        <template v-else>
          <input
            v-model="editTitle"
            class="w-full text-sm border border-gray-200 rounded px-2 py-1 focus:outline-none focus:border-accent-500"
            @keydown.enter.stop.prevent="saveEdit"
            @keydown.escape.stop="cancelEdit"
          />
          <textarea
            v-model="editNotes"
            rows="3"
            placeholder="Notes…"
            class="w-full text-sm border border-gray-200 rounded px-2 py-1 resize-none focus:outline-none focus:border-accent-500"
            @keydown.escape.stop="cancelEdit"
          />
        </template>

        <!-- Action row -->
        <div class="flex items-center gap-2 flex-wrap pt-1" v-if="!readonly">
          <template v-if="!editing">
            <button
              class="text-xs px-2 py-1 text-accent-600 hover:bg-accent-50 rounded"
              @click="startEdit"
            >
              Edit
            </button>
            <button
              v-if="task.status === 'open'"
              class="text-xs px-2 py-1 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded"
              @click="cancelTask"
            >
              Cancel task
            </button>
            <button
              v-if="task.status === 'canceled' || task.status === 'completed'"
              class="text-xs px-2 py-1 text-gray-500 hover:bg-gray-100 rounded"
              @click="reopenTask"
            >
              Reopen
            </button>
            <button
              class="ml-auto text-xs px-2 py-1 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded"
              @click="deleteTask"
            >
              Delete…
            </button>
          </template>
          <template v-else>
            <button
              class="text-xs px-2 py-1 rounded bg-accent-500 text-white hover:bg-accent-600"
              @click="saveEdit"
            >
              Save
            </button>
            <button
              class="text-xs px-2 py-1 text-gray-500 hover:text-gray-700"
              @click="cancelEdit"
            >
              Cancel
            </button>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
