import { api } from './client'

// owner: 'human' (the server default), 'agent' or 'all'.
export const getCurrentCycle = (category, owner = 'human') =>
  api.get('/cycles/current', { params: { category, owner } })

export const listCycles = (category, { limit = 50, offset = 0 } = {}) =>
  api.get('/cycles', { params: { category, limit, offset } })

export const getCycle = (cycleId, owner = 'human') =>
  api.get(`/cycles/${cycleId}`, { params: { owner } })

export const transitionCycle = (cycleId, actions) =>
  api.post(`/cycles/${cycleId}/transition`, { actions })

export const getHistory = (category, owner = 'human') =>
  api.get('/history', { params: { category, owner } })
