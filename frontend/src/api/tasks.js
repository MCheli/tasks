import { api } from './client'

export const createTask = (payload) => api.post('/tasks', payload)
export const updateTask = (id, payload) => api.patch(`/tasks/${id}`, payload)
export const deleteTask = (id) => api.delete(`/tasks/${id}`)
export const reorderTask = (id, newPosition) =>
  api.post(`/tasks/${id}/reorder`, { new_position: newPosition })
export const getTask = (id) => api.get(`/tasks/${id}`)
/** Append to a task's notes log. author is optional (defaults to the signed-in user). */
export const addNote = (id, body, author) =>
  api.post(`/tasks/${id}/notes`, author ? { body, author } : { body })
export const listTasks = (params) => api.get('/tasks', { params })
