import { api } from './client'

export const getCurrentCycle = (category) =>
  api.get('/cycles/current', { params: { category } })

export const listCycles = (category, { limit = 50, offset = 0 } = {}) =>
  api.get('/cycles', { params: { category, limit, offset } })

export const getCycle = (cycleId) => api.get(`/cycles/${cycleId}`)

export const transitionCycle = (cycleId, actions) =>
  api.post(`/cycles/${cycleId}/transition`, { actions })

// History endpoint placeholder; backend implementation in Phase 6.
export const getHistory = (category) =>
  api.get('/history', { params: { category } })
