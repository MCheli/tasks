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
const CYCLE_BAND_HEIGHT = 22 // colored cycle bar at the top of the chart
const PADDING_TOP = CYCLE_BAND_HEIGHT + 14 // band + a little breathing room
const PADDING_BOTTOM = 16
const CHART_MIN_WIDTH = 800

const STATUS_COLOR = {
  open: '#6366f1', // accent-500
  completed: '#10b981', // emerald-500
  canceled: '#9ca3af', // gray-400
}

// Alternating cycle band fills (low-saturation indigo / slate).
const CYCLE_BAND_FILLS = ['#eef2ff', '#f1f5f9']

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

function fmtShort(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  })
}

// ---------------------------------------------------------------------------
// Cycle bands — alternating colored rectangles spanning each cycle's life.
// Numbered "Cycle 1", "Cycle 2", ... in order of started_at ascending.
// ---------------------------------------------------------------------------
const cycleBands = computed(() =>
  props.cycles.map((c, i) => {
    const start = new Date(c.started_at).getTime()
    const end = c.ended_at ? new Date(c.ended_at).getTime() : Date.now()
    const x1 = xFor(start)
    const x2 = xFor(end)
    const width = Math.max(2, x2 - x1)
    const labelDate = c.ended_at
      ? `${fmtShort(c.started_at)} – ${fmtShort(c.ended_at)}`
      : `${fmtShort(c.started_at)} – now`
    return {
      id: c.id,
      x: x1,
      width,
      fill: CYCLE_BAND_FILLS[i % CYCLE_BAND_FILLS.length],
      number: i + 1,
      isCurrent: !c.ended_at,
      label: `Cycle ${i + 1}`,
      sublabel: labelDate,
    }
  })
)

// Vertical gridlines at every cycle boundary (start of each cycle).
const cycleLines = computed(() =>
  props.cycles.map((c) => ({
    id: c.id,
    x: xFor(new Date(c.started_at).getTime()),
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
      <!-- Cycle band — alternating colored rectangles labeled "Cycle 1", "Cycle 2", ... -->
      <g class="cycle-bands">
        <g
          v-for="band in cycleBands"
          :key="band.id"
        >
          <rect
            :x="band.x"
            :y="0"
            :width="band.width"
            :height="CYCLE_BAND_HEIGHT"
            :fill="band.fill"
            :stroke="band.isCurrent ? '#6366f1' : '#cbd5e1'"
            stroke-width="0.5"
          >
            <title>{{ band.label }} ({{ band.sublabel }})</title>
          </rect>
          <text
            :x="band.x + 6"
            :y="14"
            font-size="10"
            font-weight="600"
            :fill="band.isCurrent ? '#4338ca' : '#475569'"
          >
            {{ band.label }}<tspan
              dx="6"
              font-weight="400"
              fill="#94a3b8"
            >{{ band.sublabel }}</tspan>
          </text>
        </g>
      </g>

      <!-- Vertical gridlines at each cycle boundary, below the band -->
      <g class="grid">
        <line
          v-for="line in cycleLines"
          :key="line.id"
          :x1="line.x"
          :y1="CYCLE_BAND_HEIGHT"
          :x2="line.x"
          :y2="chartHeight"
          stroke="#e5e7eb"
          stroke-width="1"
        />
      </g>

      <!-- Today marker -->
      <line
        :x1="todayX"
        :y1="CYCLE_BAND_HEIGHT"
        :x2="todayX"
        :y2="chartHeight - PADDING_BOTTOM"
        stroke="#f59e0b"
        stroke-width="1"
        stroke-dasharray="2,3"
      />

      <!-- Rows -->
      <g
        v-for="row in rows"
        :key="row.key"
      >
        <!-- Label -->
        <text
          :x="LABEL_WIDTH - 8"
          :y="row.y + ROW_HEIGHT / 2 + 4"
          text-anchor="end"
          font-size="11"
          fill="#374151"
        >
          <tspan
            font-family="ui-monospace, monospace"
            fill="#9ca3af"
          >#{{ row.displayId }}</tspan>
          <tspan dx="6">{{ row.title.length > 24 ? row.title.slice(0, 23) + '…' : row.title }}</tspan>
        </text>

        <!-- Segments -->
        <g
          v-for="seg in row.segments"
          :key="seg.id"
        >
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
