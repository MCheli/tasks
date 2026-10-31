<script setup>
// The login page's picture: a few pieces of Tasks drawn with illustrative content.
// Static on purpose: it renders before sign-in and never calls the API.
const R = 30
const CIRC = 2 * Math.PI * R

const rows = [
  { id: 79, title: 'Fix the leaky bathroom faucet', status: 'open', pushed: 4 },
  { id: 103, title: 'Rebalance 401(k) back to 80/20', status: 'open', pushed: 2 },
  { id: 113, title: 'Groceries + meal prep', status: 'done' },
  { id: 123, title: 'Book the snow-tire swap', status: 'open' },
]

const triage = [
  { icon: '→', label: 'Forward', cls: 'bg-accent-500' },
  { icon: '✓', label: 'Complete', cls: 'bg-emerald-500' },
  { icon: '✗', label: 'Cancel', cls: 'bg-slate-400' },
]

// History: [start, end] as fractions of the width, and how each lineage ended.
const bars = [
  { x: 0.02, w: 0.42, end: 'done' },
  { x: 0.1, w: 0.2, end: 'done' },
  { x: 0.26, w: 0.6, end: 'open' },
  { x: 0.34, w: 0.18, end: 'canceled' },
  { x: 0.5, w: 0.24, end: 'done' },
  { x: 0.62, w: 0.24, end: 'open' },
]
const BAR = { done: '#34d399', open: '#818cf8', canceled: '#94a3b8' }
</script>

<template>
  <div
    class="relative w-full max-w-[33rem] h-[21rem] select-none"
    aria-hidden="true"
  >
    <!-- This cycle -->
    <div class="hero-card float-a absolute left-0 top-2 w-[19.5rem] p-4">
      <div class="flex items-baseline justify-between">
        <span class="text-[11px] uppercase tracking-wider text-indigo-200/80">Personal · this cycle</span>
        <span class="text-[11px] text-indigo-100/70">day 5</span>
      </div>
      <ul class="mt-2.5 space-y-2">
        <li
          v-for="r in rows"
          :key="r.id"
          class="flex items-center gap-2.5 text-[13px]"
        >
          <span
            class="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded text-[10px]"
            :class="r.status === 'done' ? 'bg-emerald-400 text-emerald-950' : 'border-[1.5px] border-white/35'"
          >{{ r.status === 'done' ? '✓' : '' }}</span>
          <span class="font-mono text-[10px] text-indigo-200/60">#{{ r.id }}</span>
          <span
            class="truncate"
            :class="r.status === 'done' ? 'text-white/45 line-through' : 'text-white'"
          >{{ r.title }}</span>
          <span
            v-if="r.pushed"
            class="ml-auto flex-shrink-0 rounded-full bg-amber-300/15 px-1.5 py-px text-[10px] text-amber-200"
          >{{ r.pushed }}× →</span>
        </li>
      </ul>
    </div>

    <!-- Triage at the end of a cycle -->
    <div class="hero-card float-b absolute left-[21rem] top-0 w-[11.5rem] p-4">
      <div class="text-[11px] uppercase tracking-wider text-indigo-200/80">New cycle</div>
      <ul class="mt-2.5 space-y-2">
        <li
          v-for="t in triage"
          :key="t.label"
          class="flex items-center gap-2.5 text-[13px] text-white"
        >
          <span
            class="flex h-6 w-6 items-center justify-center rounded-md text-xs font-bold text-white"
            :class="t.cls"
          >{{ t.icon }}</span>
          {{ t.label }}
        </li>
      </ul>
    </div>

    <!-- History: every task's lineage across cycles -->
    <div class="hero-card float-c absolute left-[11rem] bottom-0 w-[21.5rem] p-4">
      <div class="flex items-baseline justify-between">
        <span class="text-[11px] uppercase tracking-wider text-indigo-200/80">History</span>
        <span class="text-[11px] text-indigo-100/70">6 cycles</span>
      </div>
      <svg
        viewBox="0 0 300 92"
        class="mt-2 w-full h-[5.5rem]"
      >
        <rect
          v-for="i in 6"
          :key="i"
          :x="(i - 1) * 50"
          y="0"
          width="50"
          height="92"
          :fill="i % 2 ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.0)'"
        />
        <g
          v-for="(b, i) in bars"
          :key="i"
          class="grow"
          :style="{ animationDelay: `${0.15 + i * 0.12}s`, transformOrigin: `${b.x * 300}px 0` }"
        >
          <rect
            :x="b.x * 300"
            :y="4 + i * 14.5"
            :width="b.w * 300 - 9"
            height="9"
            rx="3"
            fill="#818cf8"
            opacity="0.85"
          />
          <rect
            :x="(b.x + b.w) * 300 - 12"
            :y="4 + i * 14.5"
            width="12"
            height="9"
            rx="3"
            :fill="BAR[b.end]"
          />
        </g>
        <line
          x1="262"
          y1="0"
          x2="262"
          y2="92"
          stroke="#fbbf24"
          stroke-width="1.5"
          stroke-dasharray="3 3"
          opacity="0.8"
        />
      </svg>
    </div>

    <!-- Last cycle's completion -->
    <div class="hero-card float-b absolute left-2 bottom-8 flex items-center gap-3 px-4 py-3">
      <svg
        viewBox="0 0 72 72"
        class="h-12 w-12 -rotate-90"
      >
        <circle
          cx="36"
          cy="36"
          :r="R"
          fill="none"
          stroke="rgba(255,255,255,0.12)"
          stroke-width="7"
        />
        <circle
          cx="36"
          cy="36"
          :r="R"
          fill="none"
          stroke="#34d399"
          stroke-width="7"
          stroke-linecap="round"
          :stroke-dasharray="CIRC"
          :stroke-dashoffset="CIRC * 0.18"
        />
      </svg>
      <div>
        <div class="text-sm font-semibold text-white tabular-nums">82% done</div>
        <div class="text-[11px] text-indigo-100/70">last cycle · 2 carried</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hero-card {
  border-radius: 1rem;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 0 20px 45px -20px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(10px);
}
.grow {
  transform: scaleX(0);
  animation: grow 0.9s ease-out forwards;
}
.float-a { animation: float 7s ease-in-out infinite; }
.float-b { animation: float 8s ease-in-out -2s infinite; }
.float-c { animation: float 9s ease-in-out -4s infinite; }
@keyframes grow { to { transform: scaleX(1); } }
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-8px); } }
@media (prefers-reduced-motion: reduce) {
  .float-a, .float-b, .float-c { animation: none; }
  .grow { animation: none; transform: none; }
}
</style>
