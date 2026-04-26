<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as apiKeysApi from '@/api/apiKeys'
import TabSwitcher from '@/components/TabSwitcher.vue'

const router = useRouter()

const activeTab = ref('keys')

const keys = ref([])
const loading = ref(true)
const error = ref('')

const showCreate = ref(false)
const newName = ref('')
const creating = ref(false)

const createdKey = ref(null)
const copied = ref(false)

async function loadKeys() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await apiKeysApi.listApiKeys()
    keys.value = data
  } catch (e) {
    error.value = e?.response?.data?.detail || 'Failed to load API keys'
  } finally {
    loading.value = false
  }
}

async function submitCreate() {
  const name = newName.value.trim()
  if (!name) return
  creating.value = true
  error.value = ''
  try {
    const { data } = await apiKeysApi.createApiKey(name)
    createdKey.value = data.key
    newName.value = ''
    showCreate.value = false
    await loadKeys()
  } catch (e) {
    error.value = e?.response?.data?.detail || 'Failed to create API key'
  } finally {
    creating.value = false
  }
}

async function revoke(id) {
  if (!confirm('Revoke this API key? Any clients using it will stop working.')) return
  try {
    await apiKeysApi.revokeApiKey(id)
    await loadKeys()
  } catch (e) {
    error.value = e?.response?.data?.detail || 'Failed to revoke API key'
  }
}

function copyKey() {
  if (!createdKey.value) return
  navigator.clipboard.writeText(createdKey.value)
  copied.value = true
  setTimeout(() => (copied.value = false), 2000)
}

function dismissCreated() {
  createdKey.value = null
  copied.value = false
}

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

const baseUrl = computed(() => `${window.location.origin}/api`)
const docsUrl = computed(() => `${window.location.origin}/api/docs`)

const endpoints = [
  { method: 'GET', path: '/api/auth/me', summary: 'Current authenticated user' },
  { method: 'GET', path: '/api/cycles?category=personal', summary: 'List cycles in a category' },
  { method: 'GET', path: '/api/cycles/current?category=personal', summary: 'Current open cycle' },
  { method: 'POST', path: '/api/cycles/transition', summary: 'End current cycle and start a new one' },
  { method: 'POST', path: '/api/tasks', summary: 'Create a task in the current cycle' },
  { method: 'GET', path: '/api/tasks/{task_id}', summary: 'Fetch a task with its lineage' },
  { method: 'PATCH', path: '/api/tasks/{task_id}', summary: 'Update title, notes, or status' },
  { method: 'POST', path: '/api/tasks/{task_id}/reorder', summary: 'Move a task to a new position' },
  { method: 'DELETE', path: '/api/tasks/{task_id}', summary: 'Soft-delete a task lineage' },
  { method: 'GET', path: '/api/history?category=personal', summary: 'Cycle + task lineage history' },
  { method: 'GET', path: '/api/api-keys', summary: 'List your API keys' },
  { method: 'POST', path: '/api/api-keys', summary: 'Create a new API key' },
  { method: 'DELETE', path: '/api/api-keys/{key_id}', summary: 'Revoke an API key' },
]

const methodColor = (m) => {
  if (m === 'GET') return 'bg-emerald-50 text-emerald-700'
  if (m === 'POST') return 'bg-blue-50 text-blue-700'
  if (m === 'PATCH') return 'bg-amber-50 text-amber-700'
  if (m === 'DELETE') return 'bg-red-50 text-red-700'
  return 'bg-gray-100 text-gray-700'
}

onMounted(loadKeys)
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
          Settings
        </h1>
        <TabSwitcher class="hidden sm:flex" />
      </div>
      <div class="sm:hidden border-t border-gray-100 px-3 py-2">
        <TabSwitcher />
      </div>
    </header>

    <main class="max-w-3xl mx-auto p-4 pb-24">
      <!-- Tab bar -->
      <div class="flex gap-1 mb-5">
        <button
          class="px-4 py-2 rounded-lg text-xs font-medium transition-colors"
          :class="activeTab === 'keys'
            ? 'bg-gray-900 text-white'
            : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'"
          @click="activeTab = 'keys'"
        >
          API Keys
        </button>
        <button
          class="px-4 py-2 rounded-lg text-xs font-medium transition-colors"
          :class="activeTab === 'reference'
            ? 'bg-gray-900 text-white'
            : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'"
          @click="activeTab = 'reference'"
        >
          API Reference
        </button>
      </div>

      <!-- ════ Keys Tab ════ -->
      <div v-show="activeTab === 'keys'">
        <!-- Newly-created key banner -->
        <div
          v-if="createdKey"
          class="mb-6 bg-green-50 border border-green-200 rounded-xl p-5"
        >
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-semibold text-green-800">
              API Key created
            </h3>
            <button
              class="text-green-500 hover:text-green-700 text-xs"
              @click="dismissCreated"
            >
              Dismiss
            </button>
          </div>
          <p class="text-xs text-green-700 mb-3">
            Copy this key now — it won't be shown again.
          </p>
          <div class="flex items-center gap-2">
            <code class="flex-1 px-3 py-2 text-xs font-mono bg-white border border-green-200 rounded-lg text-gray-800 select-all break-all">
              {{ createdKey }}
            </code>
            <button
              class="px-3 py-2 text-xs font-medium rounded-lg transition-colors"
              :class="copied
                ? 'bg-green-600 text-white'
                : 'bg-green-100 text-green-700 hover:bg-green-200'"
              @click="copyKey"
            >
              {{ copied ? 'Copied!' : 'Copy' }}
            </button>
          </div>
        </div>

        <div class="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <div class="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <div>
              <h3 class="text-sm font-semibold text-gray-900">
                Your API keys
              </h3>
              <p class="text-xs text-gray-400 mt-0.5">
                Each key has full access to your tasks and cycles. Treat them like passwords.
              </p>
            </div>
            <button
              class="px-3 py-1.5 text-xs font-medium rounded-lg bg-gray-900 text-white hover:bg-gray-800 transition-colors"
              @click="showCreate = !showCreate"
            >
              {{ showCreate ? 'Cancel' : 'New key' }}
            </button>
          </div>

          <div
            v-if="showCreate"
            class="px-5 py-4 border-b border-gray-100 bg-gray-50"
          >
            <label class="block text-xs font-medium text-gray-700 mb-1">
              Name
            </label>
            <input
              v-model="newName"
              type="text"
              placeholder="e.g. raycast-extension"
              class="w-full px-3 py-2 text-xs bg-white border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-gray-900"
              @keydown.enter="submitCreate"
            >
            <button
              class="mt-3 w-full px-3 py-2 text-xs font-medium rounded-lg bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50 transition-colors"
              :disabled="creating || !newName.trim()"
              @click="submitCreate"
            >
              {{ creating ? 'Creating…' : 'Create API key' }}
            </button>
          </div>

          <div
            v-if="loading"
            class="px-5 py-8 text-center text-xs text-gray-400"
          >
            Loading…
          </div>
          <div
            v-else-if="!keys.length"
            class="px-5 py-8 text-center"
          >
            <p class="text-sm text-gray-400">
              No API keys yet.
            </p>
            <p class="text-xs text-gray-300 mt-1">
              Create one to access your data programmatically.
            </p>
          </div>
          <div
            v-else
            class="divide-y divide-gray-50"
          >
            <div
              v-for="k in keys"
              :key="k.id"
              class="px-5 py-3 flex items-center justify-between"
            >
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-medium text-gray-900 truncate">{{ k.name }}</span>
                  <span
                    class="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                    :class="k.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-400'"
                  >
                    {{ k.is_active ? 'active' : 'revoked' }}
                  </span>
                </div>
                <div class="text-[10px] text-gray-400 mt-0.5 font-mono">
                  {{ k.key_prefix }}…
                  <span class="ml-2 font-sans">Created {{ fmtDate(k.created_at) }}</span>
                  <span
                    v-if="k.last_used_at"
                    class="ml-2 font-sans"
                  >Last used {{ fmtDate(k.last_used_at) }}</span>
                </div>
              </div>
              <button
                v-if="k.is_active"
                class="text-xs text-red-500 hover:text-red-600 font-medium ml-3"
                @click="revoke(k.id)"
              >
                Revoke
              </button>
            </div>
          </div>
        </div>

        <p
          v-if="error"
          class="text-xs text-red-600 mt-4"
          role="alert"
        >
          {{ error }}
        </p>
      </div>

      <!-- ════ Reference Tab ════ -->
      <div
        v-show="activeTab === 'reference'"
        class="space-y-4"
      >
        <div class="bg-white border border-gray-200 rounded-xl p-5">
          <h3 class="text-sm font-semibold text-gray-900 mb-2">
            Base URL
          </h3>
          <code class="block text-xs font-mono px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-gray-700">{{ baseUrl }}</code>
          <p class="text-[11px] text-gray-500 mt-2">
            Authenticate with the
            <code class="bg-gray-100 px-1 rounded">X-API-Key</code> header. Each key
            grants full read/write access to its owner's tasks and cycles.
          </p>
        </div>

        <div class="bg-white border border-gray-200 rounded-xl p-5">
          <h3 class="text-sm font-semibold text-gray-900 mb-3">
            Quick start
          </h3>
          <div class="space-y-3">
            <div>
              <p class="text-[11px] font-medium text-gray-600 mb-1">
                curl
              </p>
              <pre class="text-[11px] font-mono bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-x-auto text-gray-700">curl -H "X-API-Key: tsk_…" \
              {{ baseUrl }}/cycles/current?category=personal</pre>
            </div>
            <div>
              <p class="text-[11px] font-medium text-gray-600 mb-1">
                Python
              </p>
              <pre class="text-[11px] font-mono bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-x-auto text-gray-700">import requests

API_KEY = "tsk_…"
BASE = "{{ baseUrl }}"

r = requests.get(
    f"{BASE}/cycles/current",
    params={"category": "personal"},
    headers={"X-API-Key": API_KEY},
)
r.raise_for_status()
print(r.json())</pre>
            </div>
            <div>
              <p class="text-[11px] font-medium text-gray-600 mb-1">
                JavaScript
              </p>
              <pre class="text-[11px] font-mono bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-x-auto text-gray-700">const res = await fetch(
  "{{ baseUrl }}/cycles/current?category=personal",
  { headers: { "X-API-Key": "tsk_…" } }
);
const cycle = await res.json();</pre>
            </div>
          </div>
        </div>

        <div class="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <div class="px-5 py-4 border-b border-gray-100">
            <h3 class="text-sm font-semibold text-gray-900">
              Endpoints
            </h3>
            <p class="text-[11px] text-gray-500 mt-0.5">
              For full request/response schemas, open the
              <a
                :href="docsUrl"
                target="_blank"
                rel="noopener"
                class="text-blue-600 hover:underline"
              >interactive Swagger docs</a>.
            </p>
          </div>
          <table class="w-full text-xs">
            <tbody class="divide-y divide-gray-50">
              <tr
                v-for="ep in endpoints"
                :key="ep.method + ep.path"
              >
                <td class="px-5 py-2 align-top w-20">
                  <span
                    class="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded"
                    :class="methodColor(ep.method)"
                  >{{ ep.method }}</span>
                </td>
                <td class="px-2 py-2 font-mono text-gray-700 align-top whitespace-nowrap">
                  {{ ep.path }}
                </td>
                <td class="px-5 py-2 text-gray-500 align-top">
                  {{ ep.summary }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="bg-white border border-gray-200 rounded-xl p-5">
          <h3 class="text-sm font-semibold text-gray-900 mb-2">
            Errors
          </h3>
          <ul class="text-xs text-gray-600 space-y-1">
            <li>
              <code class="bg-gray-100 px-1 rounded">401 Unauthorized</code> — missing, malformed, or revoked API key.
            </li>
            <li>
              <code class="bg-gray-100 px-1 rounded">404 Not Found</code> — resource doesn't exist or belongs to another user.
            </li>
            <li>
              <code class="bg-gray-100 px-1 rounded">422 Unprocessable Entity</code> — request body failed validation.
            </li>
          </ul>
        </div>
      </div>
    </main>
  </div>
</template>
