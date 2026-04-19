<script setup>
import { useCyclesStore } from '@/stores/cycles'

const cycles = useCyclesStore()

const tabs = [
  { id: 'personal', label: 'Personal' },
  { id: 'professional', label: 'Professional' },
]
</script>

<template>
  <div role="tablist" class="flex items-center gap-0 bg-gray-100 rounded-lg p-1">
    <button
      v-for="t in tabs"
      :key="t.id"
      role="tab"
      :aria-selected="cycles.activeCategory === t.id"
      class="px-4 py-1.5 text-sm font-medium rounded-md transition-colors"
      :class="
        cycles.activeCategory === t.id
          ? 'bg-white text-accent-700 shadow-sm'
          : 'text-gray-500 hover:text-gray-700'
      "
      @click="cycles.setCategory(t.id)"
    >
      {{ t.label }}
    </button>
  </div>
</template>
