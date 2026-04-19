# Frontend Implementation

Vue 3 (Composition API, `<script setup>`) + Vite + Tailwind CSS + Pinia + Vue Router + Axios.

## Entry Point: `src/main.js`

```javascript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'

import App from './App.vue'
import { routes } from './router'
import './assets/main.css'

const app = createApp(App)
const pinia = createPinia()
const router = createRouter({ history: createWebHistory(), routes })

app.use(pinia)
app.use(router)
app.mount('#app')
```

## Router: `src/router/index.js`

```javascript
import { useAuthStore } from '@/stores/auth'

export const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
  { path: '/', redirect: '/cycle' },
  { path: '/cycle', name: 'cycle', component: () => import('@/views/CycleView.vue') },
  { path: '/cycle/transition', name: 'transition', component: () => import('@/views/TransitionView.vue') },
  { path: '/cycle/:cycleId', name: 'historical-cycle', component: () => import('@/views/CycleView.vue'), props: true },
  { path: '/history', name: 'history', component: () => import('@/views/HistoryView.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/cycle' },
]

export function installGuards(router) {
  router.beforeEach(async (to) => {
    const auth = useAuthStore()
    if (!auth.initialized) await auth.init()
    if (to.meta.public) return true
    if (!auth.user) return { name: 'login', query: { next: to.fullPath } }
    return true
  })
}
```

Call `installGuards(router)` from `main.js` after `app.use(router)`.

## Axios Client: `src/api/client.js`

```javascript
import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  withCredentials: true,  // send cookies
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !window.location.pathname.startsWith('/login')) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`
    }
    return Promise.reject(error)
  }
)
```

In dev, Vite proxies `/api` to the backend. Configure in `vite.config.js`:

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
  build: { outDir: 'dist' },
})
```

## API Modules: `src/api/*.js`

```javascript
// src/api/auth.js
import { api } from './client'
export const login = (email, password) => api.post('/auth/login', { email, password })
export const logout = () => api.post('/auth/logout')
export const me = () => api.get('/auth/me')
```

```javascript
// src/api/cycles.js
import { api } from './client'
export const getCurrentCycle = (category) => api.get('/cycles/current', { params: { category } })
export const listCycles = (category) => api.get('/cycles', { params: { category } })
export const transitionCycle = (cycleId, actions) =>
  api.post(`/cycles/${cycleId}/transition`, { actions })
export const getHistory = (category) => api.get('/history', { params: { category } })
```

```javascript
// src/api/tasks.js
import { api } from './client'
export const createTask = (payload) => api.post('/tasks', payload)
export const updateTask = (id, payload) => api.patch(`/tasks/${id}`, payload)
export const deleteTask = (id) => api.delete(`/tasks/${id}`)
export const reorderTask = (id, newPosition) => api.post(`/tasks/${id}/reorder`, null, { params: { new_position: newPosition } })
export const getTask = (id) => api.get(`/tasks/${id}`)
```

## Stores (Pinia)

### `src/stores/auth.js`

```javascript
import { defineStore } from 'pinia'
import * as authApi from '@/api/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    initialized: false,
  }),
  actions: {
    async init() {
      try {
        const { data } = await authApi.me()
        this.user = data
      } catch {
        this.user = null
      } finally {
        this.initialized = true
      }
    },
    async login(email, password) {
      const { data } = await authApi.login(email, password)
      this.user = data.user
    },
    async logout() {
      await authApi.logout()
      this.user = null
    },
  },
})
```

### `src/stores/cycles.js`

```javascript
import { defineStore } from 'pinia'
import * as cyclesApi from '@/api/cycles'

const TAB_KEY = 'cycle-todo:active-tab'

export const useCyclesStore = defineStore('cycles', {
  state: () => ({
    activeCategory: localStorage.getItem(TAB_KEY) || 'personal',
    currentCycle: null,
    tasks: { open: [], completed: [], canceled: [] },
    summary: { open: 0, completed: 0, canceled: 0 },
    loading: false,
  }),
  actions: {
    setCategory(category) {
      this.activeCategory = category
      localStorage.setItem(TAB_KEY, category)
      return this.refresh()
    },
    async refresh() {
      this.loading = true
      try {
        const { data } = await cyclesApi.getCurrentCycle(this.activeCategory)
        this.currentCycle = data.cycle
        this.tasks = data.tasks
        this.summary = data.summary
      } finally {
        this.loading = false
      }
    },
  },
})
```

Tasks store (`src/stores/tasks.js`) holds only transient UI state (currently-editing task id, etc.). Task CRUD operations mutate `useCyclesStore`'s lists directly (optimistic updates).

## Tailwind Configuration

`tailwind.config.js`:

```javascript
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        accent: {
          50: '#eef2ff', 500: '#6366f1', 600: '#4f46e5', 700: '#4338ca',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
```

`src/assets/main.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  html { scroll-behavior: smooth; }
  body { @apply bg-gray-50 text-gray-900 antialiased; }
  button:focus-visible, a:focus-visible, input:focus-visible, textarea:focus-visible {
    @apply outline-none ring-2 ring-accent-500 ring-offset-2;
  }
}
```

## Key Components

### `App.vue`

```vue
<script setup>
import { useAuthStore } from '@/stores/auth'
const auth = useAuthStore()
auth.init()  // kick off auth check on mount
</script>

<template>
  <RouterView v-slot="{ Component }">
    <Transition name="fade" mode="out-in">
      <component :is="Component" />
    </Transition>
  </RouterView>
</template>
```

### `components/TabSwitcher.vue`

```vue
<script setup>
import { useCyclesStore } from '@/stores/cycles'
const cycles = useCyclesStore()
const tabs = [
  { id: 'personal', label: 'Personal' },
  { id: 'professional', label: 'Professional' },
]
</script>

<template>
  <div class="flex gap-1 border-b border-gray-200" role="tablist">
    <button
      v-for="t in tabs"
      :key="t.id"
      role="tab"
      :aria-selected="cycles.activeCategory === t.id"
      class="px-4 py-2 text-sm font-medium transition-colors"
      :class="cycles.activeCategory === t.id
        ? 'text-accent-600 border-b-2 border-accent-500 -mb-px'
        : 'text-gray-500 hover:text-gray-700'"
      @click="cycles.setCategory(t.id)"
    >
      {{ t.label }}
    </button>
  </div>
</template>
```

### `components/TaskInput.vue`

Inline creation card that expands on focus. Same shape used for new-task and task-edit.

```vue
<script setup>
import { ref } from 'vue'
import { useCyclesStore } from '@/stores/cycles'
import * as tasksApi from '@/api/tasks'

const cycles = useCyclesStore()
const title = ref('')
const notes = ref('')
const expanded = ref(false)
const submitting = ref(false)

async function submit() {
  if (!title.value.trim() || submitting.value) return
  submitting.value = true
  try {
    const { data } = await tasksApi.createTask({
      category: cycles.activeCategory,
      title: title.value.trim(),
      notes: notes.value.trim() || null,
    })
    cycles.tasks.open.push(data.task)
    cycles.summary.open += 1
    title.value = ''
    notes.value = ''
    // keep expanded so user can add another
  } finally {
    submitting.value = false
  }
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
  if (e.key === 'Escape') { expanded.value = false }
}
</script>

<template>
  <div
    class="bg-white rounded-lg border border-gray-200 transition-all"
    :class="expanded ? 'shadow-md p-4' : 'p-2'"
  >
    <input
      v-model="title"
      type="text"
      placeholder="Add a task…"
      class="w-full border-none focus:outline-none bg-transparent text-base"
      @focus="expanded = true"
      @keydown="handleKey"
    />
    <div v-if="expanded" class="mt-3 space-y-3">
      <textarea
        v-model="notes"
        placeholder="Notes (optional)…"
        rows="3"
        class="w-full resize-none border border-gray-200 rounded p-2 text-sm focus:outline-none focus:border-accent-500"
        @keydown="handleKey"
      />
      <div class="flex justify-end gap-2">
        <button @click="expanded = false" class="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700">
          Cancel
        </button>
        <button
          @click="submit"
          :disabled="!title.trim() || submitting"
          class="px-3 py-1.5 text-sm bg-accent-500 text-white rounded hover:bg-accent-600 disabled:opacity-50"
        >
          Add
        </button>
      </div>
    </div>
  </div>
</template>
```

### `components/TaskItem.vue`

Checkbox + title + kebab menu; click-to-expand inline; drag handle; status styling.

```vue
<script setup>
import { ref } from 'vue'
import * as tasksApi from '@/api/tasks'
import { useCyclesStore } from '@/stores/cycles'

const props = defineProps({ task: Object })
const cycles = useCyclesStore()
const expanded = ref(false)
const editTitle = ref(props.task.title)
const editNotes = ref(props.task.notes || '')

async function toggleComplete() {
  const newStatus = props.task.status === 'completed' ? 'open' : 'completed'
  const { data } = await tasksApi.updateTask(props.task.id, { status: newStatus })
  cycles.refresh()  // simple re-fetch; optimistic swap can be added later
}

async function saveEdit() {
  await tasksApi.updateTask(props.task.id, { title: editTitle.value, notes: editNotes.value })
  expanded.value = false
  cycles.refresh()
}

async function cancelTask() {
  await tasksApi.updateTask(props.task.id, { status: 'canceled' })
  cycles.refresh()
}

async function deleteTask() {
  if (!confirm('Delete this task and all its history?')) return
  await tasksApi.deleteTask(props.task.id)
  cycles.refresh()
}
</script>

<template>
  <div
    class="group flex items-start gap-3 p-3 bg-white border-b border-gray-100 hover:bg-gray-50 transition-colors"
    :class="{ 'opacity-60': task.status !== 'open' }"
  >
    <button @click="toggleComplete" class="mt-1 flex-shrink-0" :aria-label="task.status === 'completed' ? 'Mark incomplete' : 'Mark complete'">
      <span v-if="task.status === 'completed'" class="w-5 h-5 rounded bg-green-500 text-white flex items-center justify-center text-xs">✓</span>
      <span v-else-if="task.status === 'canceled'" class="w-5 h-5 rounded bg-gray-400 text-white flex items-center justify-center text-xs">✗</span>
      <span v-else class="w-5 h-5 rounded border-2 border-gray-300 hover:border-accent-500" />
    </button>

    <div class="flex-1 min-w-0 cursor-pointer" @click="expanded = !expanded">
      <div class="flex items-baseline gap-2">
        <span class="text-xs text-gray-400 font-mono">#{{ task.display_id }}</span>
        <span class="text-sm" :class="{ 'line-through': task.status !== 'open' }">{{ task.title }}</span>
      </div>

      <div v-if="expanded" class="mt-3 space-y-2" @click.stop>
        <input v-model="editTitle" class="w-full border border-gray-200 rounded px-2 py-1 text-sm" />
        <textarea v-model="editNotes" rows="3" class="w-full border border-gray-200 rounded px-2 py-1 text-sm" placeholder="Notes…" />
        <div class="text-xs text-gray-400">
          Created {{ new Date(task.created_at).toLocaleDateString() }} · Pushed forward {{ task.push_forward_count }}×
        </div>
        <div class="flex gap-2">
          <button @click="saveEdit" class="px-3 py-1 text-xs bg-accent-500 text-white rounded">Save</button>
          <button @click="expanded = false" class="px-3 py-1 text-xs text-gray-500">Cancel</button>
          <button v-if="task.status === 'open'" @click="cancelTask" class="ml-auto px-3 py-1 text-xs text-gray-500 hover:text-red-500">Cancel task</button>
          <button @click="deleteTask" class="px-3 py-1 text-xs text-gray-500 hover:text-red-500">Delete</button>
        </div>
      </div>
    </div>
  </div>
</template>
```

### `views/CycleView.vue` — composition

```vue
<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useCyclesStore } from '@/stores/cycles'
import TabSwitcher from '@/components/TabSwitcher.vue'
import TaskInput from '@/components/TaskInput.vue'
import TaskItem from '@/components/TaskItem.vue'
import draggable from 'vuedraggable'

const cycles = useCyclesStore()
const router = useRouter()

onMounted(() => cycles.refresh())

async function onReorder(evt) {
  // Call /tasks/{id}/reorder — implementation here
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <header class="sticky top-0 bg-white border-b border-gray-200 z-10">
      <div class="max-w-2xl mx-auto flex items-center justify-between p-3">
        <h1 class="text-lg font-semibold">Tasks</h1>
        <TabSwitcher />
        <div class="flex gap-2">
          <button @click="router.push('/history')" aria-label="History" class="p-2 text-gray-500 hover:text-gray-700">🕐</button>
        </div>
      </div>
    </header>

    <main class="max-w-2xl mx-auto p-4 pb-24">
      <TaskInput class="mb-4" />

      <section v-if="cycles.tasks.open.length">
        <draggable :list="cycles.tasks.open" item-key="id" handle=".drag-handle" @end="onReorder">
          <template #item="{ element }">
            <TaskItem :task="element" />
          </template>
        </draggable>
      </section>
      <div v-else class="text-center text-gray-400 py-8">No open tasks. Add one above.</div>

      <section v-if="cycles.tasks.completed.length" class="mt-8">
        <h3 class="text-xs uppercase text-gray-500 font-medium mb-2">Completed ({{ cycles.tasks.completed.length }})</h3>
        <TaskItem v-for="t in cycles.tasks.completed" :key="t.id" :task="t" />
      </section>

      <section v-if="cycles.tasks.canceled.length" class="mt-8">
        <h3 class="text-xs uppercase text-gray-500 font-medium mb-2">Canceled ({{ cycles.tasks.canceled.length }})</h3>
        <TaskItem v-for="t in cycles.tasks.canceled" :key="t.id" :task="t" />
      </section>
    </main>

    <button
      @click="router.push('/cycle/transition')"
      class="fixed bottom-6 right-6 bg-accent-500 text-white px-6 py-3 rounded-full shadow-lg hover:bg-accent-600 transition-colors"
    >
      Start New Cycle
    </button>
  </div>
</template>
```

### `views/TransitionView.vue`

Implementation sketch — reuse TaskItem-style layout but replace the checkbox with a three-state cycler.

```vue
<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useCyclesStore } from '@/stores/cycles'
import * as cyclesApi from '@/api/cycles'

const router = useRouter()
const cycles = useCyclesStore()
const actions = ref({})  // persistent_task_id -> 'forward' | 'complete' | 'cancel'

onMounted(async () => {
  await cycles.refresh()
  cycles.tasks.open.forEach(t => { actions.value[t.persistent_task_id] = 'forward' })
})

const summary = computed(() => {
  const out = { forward: 0, complete: 0, cancel: 0 }
  Object.values(actions.value).forEach(a => { out[a] += 1 })
  return out
})

function cycleAction(pid) {
  const order = ['forward', 'complete', 'cancel']
  const i = order.indexOf(actions.value[pid])
  actions.value[pid] = order[(i + 1) % order.length]
}

async function startCycle() {
  if (!confirm('Start a new cycle? The current cycle will be closed.')) return
  const payload = Object.entries(actions.value).map(([pid, action]) => ({ persistent_task_id: pid, action }))
  await cyclesApi.transitionCycle(cycles.currentCycle.id, payload)
  await cycles.refresh()
  router.push('/cycle')
}

const iconFor = (a) => a === 'forward' ? '→' : a === 'complete' ? '✓' : '✗'
const colorFor = (a) => a === 'forward' ? 'bg-accent-500' : a === 'complete' ? 'bg-green-500' : 'bg-gray-400'
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <header class="sticky top-0 bg-white border-b border-gray-200 z-10 p-3">
      <div class="max-w-2xl mx-auto flex items-center justify-between">
        <button @click="router.push('/cycle')" class="text-sm text-gray-500">← Cancel</button>
        <h1 class="font-semibold capitalize">{{ cycles.activeCategory }} · New Cycle</h1>
        <div></div>
      </div>
      <div class="max-w-2xl mx-auto mt-2 text-xs text-gray-500">
        → {{ summary.forward }} forwarding · ✓ {{ summary.complete }} completing · ✗ {{ summary.cancel }} canceling
      </div>
    </header>

    <main class="max-w-2xl mx-auto p-4 pb-24">
      <div v-for="task in cycles.tasks.open" :key="task.id" class="flex items-start gap-3 p-3 bg-white border-b">
        <button
          @click="cycleAction(task.persistent_task_id)"
          class="w-8 h-8 rounded flex items-center justify-center text-white font-bold"
          :class="colorFor(actions[task.persistent_task_id])"
        >
          {{ iconFor(actions[task.persistent_task_id]) }}
        </button>
        <div class="flex-1">
          <span class="text-xs text-gray-400 font-mono">#{{ task.display_id }}</span>
          <span class="ml-2 text-sm">{{ task.title }}</span>
        </div>
      </div>
      <div v-if="!cycles.tasks.open.length" class="text-center text-gray-400 py-8">No open tasks to triage.</div>
    </main>

    <button
      @click="startCycle"
      class="fixed bottom-6 right-6 bg-accent-500 text-white px-6 py-3 rounded-full shadow-lg"
    >
      Start New Cycle
    </button>
  </div>
</template>
```

## `package.json` essentials

```json
{
  "name": "cycle-todo-frontend",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "lint": "eslint src --ext .vue,.js",
    "format": "prettier --write src"
  },
  "dependencies": {
    "vue": "^3.4.0",
    "vue-router": "^4.2.0",
    "pinia": "^2.1.0",
    "axios": "^1.6.0",
    "vuedraggable": "^4.1.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "vite": "^5.0.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0",
    "eslint": "^8.56.0",
    "eslint-plugin-vue": "^9.19.0",
    "prettier": "^3.1.0"
  }
}
```

## Keyboard Shortcuts Composable

```javascript
// src/composables/useKeyboardShortcuts.js
import { onMounted, onUnmounted } from 'vue'

export function useKeyboardShortcuts(handlers) {
  function onKey(e) {
    const inInput = ['INPUT', 'TEXTAREA'].includes(e.target.tagName)
    const key = (e.ctrlKey || e.metaKey ? 'mod+' : '') + e.key.toLowerCase()
    const fn = handlers[key]
    if (fn) {
      if (inInput && !fn.allowInInput) return
      e.preventDefault()
      fn(e)
    }
  }
  onMounted(() => window.addEventListener('keydown', onKey))
  onUnmounted(() => window.removeEventListener('keydown', onKey))
}
```

Usage in `CycleView.vue`:

```javascript
useKeyboardShortcuts({
  'n': () => document.querySelector('input[placeholder="Add a task…"]')?.focus(),
})
```

## Notes

- Keep components under 200 lines. If they grow, split into sub-components.
- Don't fetch in components — use stores. Components dispatch actions and render store state.
- Optimistic updates over spinners where possible. Revert on error.
- All timestamps from the API are ISO strings in UTC. Format in the UI with `toLocaleDateString()` / `toLocaleString()` and accept the browser's locale.
