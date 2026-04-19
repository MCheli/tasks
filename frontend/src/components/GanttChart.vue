<script setup>
import { computed } from 'vue'

const props = defineProps({
  cycles: { type: Array, required: true }, // [{id, started_at, ended_at}]
  lineages: { type: Array, required: true }, // see history schema
})

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------
const ROW_HEIGHT = 28
const ROW_GAP = 4
const LABEL_WIDTH = 220 // px reserved on the left for "#42  Title"
const PADDING_TOP = 32
const PADDING_BOTTOM = 16
const CHART_MIN_WIDTH = 800

const STATUS_COLOR = {
  open: '#6366f1', // accent-500
  completed: '#10b981', // emerald-500
  canceled: '#9ca3af', // gray-400
}

// ---------------------------------------------------------------------------
// Time scale
// ---------------------------------------------------------------------------
const timeBounds = computed(() => {
  const now = Date.now()
  const stamps = []
  for (const c of props.cycles) {
    stamps.push(new Date(c.started_at).getTime())
    if (c.ended_at) stamps.push(new Date(c.ended_at).getTime())
  }
  for (const l of props.lineages) {
    stamps.push(new Date(l.first_seen_at).getTime())
    stamps.push(new Date(l.last_seen_at).getTime())
  }
  if (!stamps.length) return { min: now - 7 * 86400000, max: now }
  const min = Math.min(...stamps)
  const max = Math.max(...stamps, now)
  // Pad 5% on either side so bars don't kiss the edges.
  const pad = (max - min) * 0.05 || 86400000
  return { min: min - pad, max: max + pad }
})

const chartHeight = computed(() => {
  const rows = Math.max(props.lineages.length, 1)
  return PADDING_TOP + rows * (ROW_HEIGHT + ROW_GAP) + PADDING_BOTTOM
})

const chartWidth = computed(() => CHART_MIN_WIDTH)

function xFor(ms) {
  const { min, max } = timeBounds.value
  const span = max - min
  const ratio = span > 0 ? (ms - min) / span : 0
  return LABEL_WIDTH + ratio * (chartWidth.value - LABEL_WIDTH - 8)
}

const todayX = computed(() => xFor(Date.now()))

// ---------------------------------------------------------------------------
// Cycle gridlines
// ---------------------------------------------------------------------------
const cycleLines = computed(() =>
  props.cycles.map((c) => ({
    id: c.id,
    x: xFor(new Date(c.started_at).getTime()),
    label: new Date(c.started_at).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
    }),
  }))
)

// ---------------------------------------------------------------------------
// Lineage rows
// ---------------------------------------------------------------------------
const rows = computed(() =>
  props.lineages.map((lineage, i) => {
    const y = PADDING_TOP + i * (ROW_HEIGHT + ROW_GAP)
    const segments = lineage.spans.map((s) => {
      const start = new Date(s.started_at).getTime()
      const end = s.ended_at ? new Date(s.ended_at).getTime() : Date.now()
      const x1 = xFor(start)
      const x2 = xFor(end)
      return {
        id: s.cycle_id,
        x: x1,
        width: Math.max(2, x2 - x1),
        color: STATUS_COLOR[s.status_at_end] || STATUS_COLOR.open,
        status: s.status_at_end,
        startedLabel: new Date(s.started_at).toLocaleDateString(),
        endedLabel: s.ended_at ? new Date(s.ended_at).toLocaleDateString() : 'now',
      }
    })
    return {
      key: lineage.persistent_task_id,
      y,
      label: `#${lineage.display_id}  ${lineage.title}`,
      title: lineage.title,
      displayId: lineage.display_id,
      latestStatus: lineage.latest_status,
      pushForward: lineage.push_forward_count,
      segments,
    }
  })
)
</script>

<template>
  <div class="overflow-x-auto bg-white rounded-lg border border-gray-200">
    <svg
      :width="chartWidth"
      :height="chartHeight"
      class="block"
      role="img"
      aria-label="Task lineage timeline"
    >
      <!-- Cycle gridlines -->
      <g class="grid">
        <line
          v-for="line in cycleLines"
          :key="line.id"
          :x1="line.x"
          :y1="0"
          :x2="line.x"
          :y2="chartHeight"
          stroke="#e5e7eb"
          stroke-width="1"
        />
        <text
          v-for="line in cycleLines"
          :key="`label-${line.id}`"
          :x="line.x + 3"
          :y="14"
          font-size="10"
          fill="#9ca3af"
        >{{ line.label }}</text>
      </g>

      <!-- Today marker -->
      <line
        :x1="todayX"
        :y1="PADDING_TOP - 4"
        :x2="todayX"
        :y2="chartHeight - PADDING_BOTTOM"
        stroke="#f59e0b"
        stroke-width="1"
        stroke-dasharray="2,3"
      />

      <!-- Rows -->
      <g v-for="row in rows" :key="row.key">
        <!-- Label -->
        <text
          :x="LABEL_WIDTH - 8"
          :y="row.y + ROW_HEIGHT / 2 + 4"
          text-anchor="end"
          font-size="11"
          fill="#374151"
        >
          <tspan font-family="ui-monospace, monospace" fill="#9ca3af">#{{ row.displayId }}</tspan>
          <tspan dx="6">{{ row.title.length > 24 ? row.title.slice(0, 23) + '…' : row.title }}</tspan>
        </text>

        <!-- Segments -->
        <g v-for="seg in row.segments" :key="seg.id">
          <rect
            :x="seg.x"
            :y="row.y + 6"
            :width="seg.width"
            :height="ROW_HEIGHT - 12"
            :fill="seg.color"
            rx="3"
            ry="3"
            opacity="0.9"
          >
            <title>{{ row.title }} — {{ seg.status }} ({{ seg.startedLabel }} → {{ seg.endedLabel }})</title>
          </rect>
        </g>
      </g>

      <!-- Empty state -->
      <text
        v-if="!rows.length"
        :x="chartWidth / 2"
        :y="chartHeight / 2"
        text-anchor="middle"
        font-size="13"
        fill="#9ca3af"
      >No history yet.</text>
    </svg>
  </div>
</template>
