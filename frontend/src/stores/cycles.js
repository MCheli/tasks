import { defineStore } from 'pinia'
import * as cyclesApi from '@/api/cycles'

const TAB_KEY = 'tasks:active-tab'
const SHOW_RESOLVED_KEY = 'tasks:show-resolved'

export const useCyclesStore = defineStore('cycles', {
  state: () => ({
    activeCategory: localStorage.getItem(TAB_KEY) || 'personal',
    showResolved: localStorage.getItem(SHOW_RESOLVED_KEY) === 'true',
    currentCycle: null,
    tasks: { open: [], completed: [], canceled: [] },
    summary: { open: 0, completed: 0, canceled: 0 },
    loading: false,
    error: null,
  }),
  actions: {
    async setCategory(category) {
      if (category === this.activeCategory) return
      this.activeCategory = category
      localStorage.setItem(TAB_KEY, category)
      await this.refresh()
    },
    toggleShowResolved() {
      this.showResolved = !this.showResolved
      localStorage.setItem(SHOW_RESOLVED_KEY, String(this.showResolved))
    },
    async refresh() {
      this.loading = true
      this.error = null
      try {
        const { data } = await cyclesApi.getCurrentCycle(this.activeCategory)
        this.currentCycle = data.cycle
        this.tasks = data.tasks
        this.summary = data.summary
      } catch (e) {
        this.error = e?.response?.data?.detail || 'Failed to load tasks'
      } finally {
        this.loading = false
      }
    },
    /** Insert a task into local state without a refetch (optimistic create). */
    insertTask(task) {
      this.tasks.open.push(task)
      this.summary.open += 1
    },
    /** Replace a task in local state by id (optimistic update). */
    replaceTask(updated) {
      for (const group of ['open', 'completed', 'canceled']) {
        const idx = this.tasks[group].findIndex((t) => t.id === updated.id)
        if (idx !== -1) {
          // Remove from current group then re-place into the right group.
          this.tasks[group].splice(idx, 1)
          this.summary[group] -= 1
          break
        }
      }
      this.tasks[updated.status].push(updated)
      this.tasks[updated.status].sort((a, b) => a.position - b.position)
      this.summary[updated.status] += 1
    },
    removeTask(taskId) {
      for (const group of ['open', 'completed', 'canceled']) {
        const idx = this.tasks[group].findIndex((t) => t.id === taskId)
        if (idx !== -1) {
          this.tasks[group].splice(idx, 1)
          this.summary[group] -= 1
          break
        }
      }
    },
    /** Replace the open list (e.g. after a drag reorder). */
    replaceOpen(tasks) {
      this.tasks.open = [...tasks]
      this.summary.open = tasks.length
    },
  },
})
