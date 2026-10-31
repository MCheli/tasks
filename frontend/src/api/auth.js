import { api } from './client'

export const login = (email, password) => api.post('/auth/login', { email, password })
export const demoLogin = () => api.post('/auth/demo')
export const logout = () => api.post('/auth/logout')
export const me = () => api.get('/auth/me')
export const config = () => api.get('/auth/config')
