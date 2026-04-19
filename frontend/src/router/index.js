// Lazy-loaded routes; views are added in later phases.
import { useAuthStore } from '@/stores/auth'

export const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true },
  },
  { path: '/', redirect: '/cycle' },
  {
    path: '/cycle',
    name: 'cycle',
    component: () => import('@/views/CycleView.vue'),
  },
  {
    path: '/cycle/transition',
    name: 'transition',
    component: () => import('@/views/TransitionView.vue'),
  },
  {
    path: '/cycle/:cycleId',
    name: 'historical-cycle',
    component: () => import('@/views/CycleView.vue'),
    props: true,
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('@/views/HistoryView.vue'),
  },
  { path: '/:pathMatch(.*)*', redirect: '/cycle' },
]

export function installGuards(router) {
  router.beforeEach(async (to) => {
    const auth = useAuthStore()
    if (!auth.initialized) await auth.init()
    if (to.meta.public) return true
    if (!auth.user) return { name: 'login', query: { next: to.fullPath } }
    return true
  })
}
