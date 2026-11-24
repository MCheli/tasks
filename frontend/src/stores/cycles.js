import { defineStore } from 'pinia'
import * as cyclesApi from '@/api/cycles'

const TAB_KEY = 'tasks:active-tab'
const OWNER_KEY = 'tasks:active-owner'
const SHOW_RESOLVED_KEY = 'tasks:show-resolved'

const GROUPS = ['open', 'completed', 'canceled']
export const OWNERS = ['human', 'agent']

const emptyGroups = () => ({ open: [], completed: [], canceled: [] })

/** Split one cycle's task groups (owner=all) into Mark's items and the agents' items. */
export function splitByOwner(groups) {
  const out = { human: emptyGroups(), agent: emptyGroups() }
  for (const g of GROUPS) {
    for (const t of groups?.[g] || []) {
      const owner = t.owner === 'agent' ? 'agent' : 'human'
      out[owner][g].push(t)
    }
  }
  return out
}

/** Counts per group; agent items also count in_progress and blocked among the open ones. */
export function summarize(groups, owner) {
  const s = {
    open: groups.open.length,
    completed: groups.completed.length,
    canceled: groups.canceled.length,
  }
  if (owner === 'agent') {
    s.in_progress = groups.open.filter((t) => t.agent_status === 'in_progress').length
    s.blocked = groups.open.filter((t) => t.agent_status === 'blocked').length
  }
  return s
}

const storedOwner = () => {
  const v = localStorage.getItem(OWNER_KEY)
  return OWNERS.includes(v) ? v : 'human'
}

export const useCyclesStore = defineStore('cycles', {
  state: () => ({
    activeCategory: localStorage.getItem(TAB_KEY) || 'personal',
    // Which part of the list is showing: Mark's own items ("human") or the agents' ("agent").
    activeOwner: storedOwner(),
    showResolved: localStorage.getItem(SHOW_RESOLVED_KEY) === 'true',
    currentCycle: null,
    // Mark's items, as before.
    tasks: emptyGroups(),
    summary: { open: 0, completed: 0, canceled: 0 },
    // The agents' follow-up items in the same cycle.
    agentTasks: emptyGroups(),
    agentSummary: { open: 0, completed: 0, canceled: 0, in_progress: 0, blocked: 0 },
    loading: false,
    error: null,
  }),
  getters: {
    /** The groups and summary of whichever owner is showing. */
    visibleTasks: (state) => (state.activeOwner === 'agent' ? state.agentTasks : state.tasks),
    visibleSummary: (state) => (state.activeOwner === 'agent' ? state.agentSummary : state.summary),
  },
  actions: {
    async setCategory(category) {
      if (category === this.activeCategory) return
      this.activeCategory = category
      localStorage.setItem(TAB_KEY, category)
      await this.refresh()
    },
    setOwner(owner) {
      if (!OWNERS.includes(owner) || owner === this.activeOwner) return
      this.activeOwner = owner
      localStorage.setItem(OWNER_KEY, owner)
    },
    toggleShowResolved() {
      this.showResolved = !this.showResolved
      localStorage.setItem(SHOW_RESOLVED_KEY, String(this.showResolved))
    },
    _recount() {
      this.summary = summarize(this.tasks, 'human')
      this.agentSummary = summarize(this.agentTasks, 'agent')
    },
    async refresh() {
      this.loading = true
      this.error = null
      try {
        const { data } = await cyclesApi.getCurrentCycle(this.activeCategory, 'all')
        this.currentCycle = data.cycle
        const split = splitByOwner(data.tasks)
        this.tasks = split.human
        this.agentTasks = split.agent
        this._recount()
      } catch (e) {
        this.error = e?.response?.data?.detail || 'Failed to load tasks'
      } finally {
        this.loading = false
      }
    },
    _groupsFor(task) {
      return task.owner === 'agent' ? this.agentTasks : this.tasks
    },
    /** Insert a task into local state without a refetch (optimistic create). */
    insertTask(task) {
      this._groupsFor(task)[task.status].push(task)
      this._recount()
    },
    /** Replace a task in local state by id (optimistic update). */
    replaceTask(updated) {
      this.removeTask(updated.id)
      const groups = this._groupsFor(updated)
      groups[updated.status].push(updated)
      groups[updated.status].sort((a, b) => a.position - b.position)
      this._recount()
    },
    removeTask(taskId) {
      for (const groups of [this.tasks, this.agentTasks]) {
        for (const g of GROUPS) {
          const idx = groups[g].findIndex((t) => t.id === taskId)
          if (idx !== -1) {
            groups[g].splice(idx, 1)
            this._recount()
            return
          }
        }
      }
    },
    /** Replace Mark's open list (e.g. after a drag reorder). */
    replaceOpen(tasks) {
      this.tasks.open = [...tasks]
      this._recount()
    },
  },
})
