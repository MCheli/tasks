<script setup>
import { ref, nextTick, watch, onUnmounted } from 'vue'
import { useCyclesStore } from '@/stores/cycles'
import * as tasksApi from '@/api/tasks'

const cycles = useCyclesStore()
const title = ref('')
const notes = ref('')
const expanded = ref(false)
const submitting = ref(false)
const titleEl = ref(null)
const notesEl = ref(null)

function onWindowKey(e) {
  if (e.key === 'Escape' && expanded.value) {
    e.preventDefault()
    collapse()
  }
}

watch(expanded, (isOpen) => {
  if (isOpen) {
    window.addEventListener('keydown', onWindowKey)
  } else {
    window.removeEventListener('keydown', onWindowKey)
  }
})

onUnmounted(() => window.removeEventListener('keydown', onWindowKey))

async function submit() {
  if (!title.value.trim() || submitting.value) return
  submitting.value = true
  try {
    const { data } = await tasksApi.createTask({
      category: cycles.activeCategory,
      title: title.value.trim(),
      notes: notes.value.trim() || null,
    })
    cycles.insertTask(data.task)
    title.value = ''
    notes.value = ''
    await nextTick()
    titleEl.value?.focus()
  } catch (e) {
    // Surface in cycles.error so the toast layer can pick it up later.
    cycles.error = e?.response?.data?.detail || 'Failed to add task'
  } finally {
    submitting.value = false
  }
}

function onTitleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  } else if (e.key === 'Enter' && e.shiftKey) {
    e.preventDefault()
    notesEl.value?.focus()
  } else if (e.key === 'Escape') {
    collapse()
  }
}

function onNotesKey(e) {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault()
    submit()
  } else if (e.key === 'Escape') {
    collapse()
  }
}

function collapse() {
  expanded.value = false
  titleEl.value?.blur()
}

defineExpose({ focus: () => titleEl.value?.focus() })
</script>

<template>
  <div
    class="bg-white rounded-lg border transition-all"
    :class="expanded ? 'shadow-sm border-gray-300 p-3' : 'border-gray-200 p-2'"
  >
    <input
      ref="titleEl"
      v-model="title"
      type="text"
      placeholder="Add a task…"
      class="w-full bg-transparent border-none focus:outline-none text-sm placeholder-gray-400"
      @focus="expanded = true"
      @keydown="onTitleKey"
    >
    <div
      v-if="expanded"
      class="mt-2 space-y-2"
    >
      <textarea
        ref="notesEl"
        v-model="notes"
        rows="2"
        placeholder="Notes (optional)"
        class="w-full text-sm border border-gray-200 rounded p-2 resize-none focus:outline-none focus:border-accent-500"
        @keydown="onNotesKey"
      />
      <div class="flex items-center justify-between">
        <p class="text-[10px] uppercase tracking-wide text-gray-400">
          Enter to save · Shift+Enter for notes · Esc to cancel
        </p>
        <div class="flex gap-2">
          <button
            type="button"
            class="px-3 py-1 text-xs text-gray-500 hover:text-gray-700"
            @click="collapse"
          >
            Cancel
          </button>
          <button
            type="button"
            class="px-3 py-1 text-xs rounded bg-accent-500 text-white font-medium hover:bg-accent-600 disabled:opacity-50"
            :disabled="!title.trim() || submitting"
            @click="submit"
          >
            {{ submitting ? 'Adding…' : 'Add' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
