import { api } from './client'

export const login = (email, password) => api.post('/auth/login', { email, password })
export const logout = () => api.post('/auth/logout')
export const me = () => api.get('/auth/me')
