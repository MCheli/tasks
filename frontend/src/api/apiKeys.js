import { api } from './client'

export const listApiKeys = () => api.get('/api-keys')
export const createApiKey = (name) => api.post('/api-keys', { name })
export const revokeApiKey = (id) => api.delete(`/api-keys/${id}`)
