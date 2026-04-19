<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as cyclesApi from '@/api/cycles'
import { useCyclesStore } from '@/stores/cycles'
import GanttChart from '@/components/GanttChart.vue'
import TabSwitcher from '@/components/TabSwitcher.vue'

const router = useRouter()
const cycles = useCyclesStore()

const loading = ref(false)
const error = ref('')
const data = ref({ cycles: [], lineages: [] })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data: resp } = await cyclesApi.getHistory(cycles.activeCategory)
    data.value = resp
  } catch (e) {
    error.value = e?.response?.data?.detail || 'Failed to load history'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => cycles.activeCategory, load)
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <header class="sticky top-0 z-10 bg-white border-b border-gray-200">
      <div class="max-w-3xl mx-auto px-3 py-2 flex items-center justify-between gap-3">
        <button
          class="text-sm text-gray-500 hover:text-gray-700"
          @click="router.push('/cycle')"
        >
          ← Back
        </button>
        <h1 class="text-base font-semibold">
          History
        </h1>
        <TabSwitcher class="hidden sm:flex" />
      </div>
      <div class="sm:hidden border-t border-gray-100 px-3 py-2">
        <TabSwitcher />
      </div>
    </header>

    <main class="max-w-3xl mx-auto p-4">
      <div
        v-if="loading"
        class="text-sm text-gray-400 text-center py-12"
      >
        Loading…
      </div>
      <div
        v-else-if="error"
        class="text-sm text-red-600 text-center py-12"
        role="alert"
      >
        {{ error }}
      </div>
      <div
        v-else-if="!data.lineages.length"
        class="text-sm text-gray-400 text-center py-12 bg-white rounded-lg border border-gray-200"
      >
        No cycles yet. Add some tasks and start a cycle to see history.
      </div>
      <GanttChart
        v-else
        :cycles="data.cycles"
        :lineages="data.lineages"
      />

      <!-- Legend -->
      <div
        v-if="data.lineages.length"
        class="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500"
      >
        <span class="inline-flex items-center gap-1.5">
          <span class="w-3 h-3 rounded-sm bg-accent-500" /> Open / forwarded
        </span>
        <span class="inline-flex items-center gap-1.5">
          <span class="w-3 h-3 rounded-sm bg-green-500" /> Completed
        </span>
        <span class="inline-flex items-center gap-1.5">
          <span class="w-3 h-3 rounded-sm bg-gray-400" /> Canceled
        </span>
        <span class="inline-flex items-center gap-1.5">
          <span class="w-3 h-3 border-l-2 border-dashed border-amber-400" /> Today
        </span>
      </div>
    </main>
  </div>
</template>
