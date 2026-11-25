<script setup>
import { useCyclesStore } from '@/stores/cycles'

const cycles = useCyclesStore()
</script>

<template>
  <!-- Mine / Agents: the two parts of the current list. The badge counts open agent items. -->
  <div
    role="tablist"
    aria-label="Whose items"
    class="inline-flex items-center bg-gray-100 rounded-lg p-0.5 text-sm"
  >
    <button
      role="tab"
      data-testid="owner-human"
      :aria-selected="cycles.activeOwner === 'human'"
      class="px-3 py-1 touch:min-h-11 rounded-md font-medium transition-colors"
      :class="
        cycles.activeOwner === 'human'
          ? 'bg-white text-gray-900 shadow-sm'
          : 'text-gray-500 hover:text-gray-700'
      "
      @click="cycles.setOwner('human')"
    >
      Mine
    </button>
    <button
      role="tab"
      data-testid="owner-agent"
      :aria-selected="cycles.activeOwner === 'agent'"
      class="px-3 py-1 touch:min-h-11 rounded-md font-medium transition-colors inline-flex items-center gap-1.5"
      :class="
        cycles.activeOwner === 'agent'
          ? 'bg-white text-gray-900 shadow-sm'
          : 'text-gray-500 hover:text-gray-700'
      "
      @click="cycles.setOwner('agent')"
    >
      Agents
      <span
        v-if="cycles.agentSummary.open"
        data-testid="agent-open-count"
        class="min-w-[1.25rem] px-1.5 py-px rounded-full text-[11px] font-semibold tabular-nums"
        :class="
          cycles.agentSummary.blocked
            ? 'bg-amber-100 text-amber-800'
            : 'bg-accent-100 text-accent-700'
        "
        :title="
          cycles.agentSummary.blocked
            ? `${cycles.agentSummary.open} open, ${cycles.agentSummary.blocked} blocked`
            : `${cycles.agentSummary.open} open`
        "
      >{{ cycles.agentSummary.open }}</span>
    </button>
  </div>
</template>
