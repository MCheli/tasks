import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/cycles', () => ({
  getCurrentCycle: vi.fn(),
}))

import * as cyclesApi from '@/api/cycles'
import { splitByOwner, summarize, useCyclesStore } from '@/stores/cycles'

const task = (id, owner, status = 'open', extra = {}) => ({
  id,
  owner,
  status,
  position: Number(id.replace(/\D/g, '')) || 0,
  agent_status: owner === 'agent' ? (status === 'completed' ? 'done' : 'open') : null,
  ...extra,
})

describe('splitByOwner / summarize', () => {
  it('separates the two parts of a list and counts agent states', () => {
    const groups = {
      open: [
        task('h1', 'human'),
        task('a1', 'agent', 'open', { agent_status: 'blocked' }),
        task('a2', 'agent'),
      ],
      completed: [task('a3', 'agent', 'completed')],
      canceled: [task('h2', 'human', 'canceled')],
    }
    const split = splitByOwner(groups)
    expect(split.human.open.map((t) => t.id)).toEqual(['h1'])
    expect(split.human.canceled.map((t) => t.id)).toEqual(['h2'])
    expect(split.agent.open.map((t) => t.id)).toEqual(['a1', 'a2'])
    expect(split.agent.completed.map((t) => t.id)).toEqual(['a3'])
    expect(summarize(split.human, 'human')).toEqual({ open: 1, completed: 0, canceled: 1 })
    expect(summarize(split.agent, 'agent')).toEqual({
      open: 2,
      completed: 1,
      canceled: 0,
      in_progress: 0,
      blocked: 1,
    })
  })

  it('treats rows without an owner as human (older API responses)', () => {
    const split = splitByOwner({ open: [{ id: 'x', status: 'open', position: 0 }] })
    expect(split.human.open).toHaveLength(1)
    expect(split.agent.open).toHaveLength(0)
  })
})

describe('cycles store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    cyclesApi.getCurrentCycle.mockReset()
  })

  it('fetches both owners in one call and keeps them apart', async () => {
    cyclesApi.getCurrentCycle.mockResolvedValue({
      data: {
        cycle: { id: 'c1', started_at: new Date().toISOString() },
        tasks: { open: [task('h1', 'human'), task('a1', 'agent')], completed: [], canceled: [] },
        summary: { open: 2, completed: 0, canceled: 0 },
      },
    })
    const store = useCyclesStore()
    await store.refresh()
    expect(cyclesApi.getCurrentCycle).toHaveBeenCalledWith('personal', 'all')
    expect(store.tasks.open.map((t) => t.id)).toEqual(['h1'])
    expect(store.agentTasks.open.map((t) => t.id)).toEqual(['a1'])
    expect(store.summary.open).toBe(1)
    expect(store.agentSummary.open).toBe(1)
    expect(store.visibleTasks.open.map((t) => t.id)).toEqual(['h1'])
    store.setOwner('agent')
    expect(store.visibleTasks.open.map((t) => t.id)).toEqual(['a1'])
    expect(localStorage.getItem('tasks:active-owner')).toBe('agent')
  })

  it('moves an agent item between groups when its status changes, and removes it on delete', () => {
    const store = useCyclesStore()
    store.insertTask(task('a1', 'agent'))
    store.insertTask(task('h1', 'human'))
    expect(store.agentSummary.open).toBe(1)
    store.replaceTask(task('a1', 'agent', 'completed'))
    expect(store.agentTasks.open).toHaveLength(0)
    expect(store.agentTasks.completed).toHaveLength(1)
    expect(store.agentSummary).toEqual({
      open: 0,
      completed: 1,
      canceled: 0,
      in_progress: 0,
      blocked: 0,
    })
    expect(store.summary.open).toBe(1)
    store.removeTask('a1')
    expect(store.agentTasks.completed).toHaveLength(0)
    store.removeTask('h1')
    expect(store.summary.open).toBe(0)
  })

  it('ignores an unknown owner value from storage', () => {
    localStorage.setItem('tasks:active-owner', 'robots')
    const store = useCyclesStore()
    expect(store.activeOwner).toBe('human')
    store.setOwner('robots')
    expect(store.activeOwner).toBe('human')
  })
})
