import { api } from './client'

export const createTask = (payload) => api.post('/tasks', payload)
export const updateTask = (id, payload) => api.patch(`/tasks/${id}`, payload)
export const deleteTask = (id) => api.delete(`/tasks/${id}`)
export const reorderTask = (id, newPosition) =>
  api.post(`/tasks/${id}/reorder`, { new_position: newPosition })
export const getTask = (id) => api.get(`/tasks/${id}`)
