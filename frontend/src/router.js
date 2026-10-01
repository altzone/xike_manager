import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/Login.vue') },
  { path: '/setup', name: 'setup', component: () => import('./views/Setup.vue') },
  {
    path: '/',
    component: () => import('./views/Layout.vue'),
    meta: { auth: true },
    children: [
      { path: '', name: 'dashboard', component: () => import('./views/Dashboard.vue'), meta: { title: 'dash.title' } },
      { path: 'users', name: 'users', component: () => import('./views/Users.vue'), meta: { admin: true, title: 'users.title' } },
      { path: 'switch/:id', name: 'switch', component: () => import('./views/SwitchView.vue'),
        children: [
          { path: '', name: 'switch-dashboard', component: () => import('./views/SwitchDashboard.vue'), meta: { title: 'nav.overview' } },
          { path: 'ports', name: 'switch-ports', component: () => import('./views/Ports.vue'), meta: { title: 'ports.title' } },
          { path: 'vlans', name: 'switch-vlans', component: () => import('./views/Vlans.vue'), meta: { title: 'vlans.title' } },
          { path: 'lag', name: 'switch-lag', component: () => import('./views/Lag.vue'), meta: { title: 'lag.title' } },
          { path: 'monitoring', name: 'switch-monitoring', component: () => import('./views/Monitoring.vue'), meta: { title: 'mac.title' } },
          { path: 'system', name: 'switch-system', component: () => import('./views/System.vue'), meta: { title: 'sys.title' } },
        ]
      },
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  const token = localStorage.getItem('token')
  if (to.meta.auth && !token) return { name: 'login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : {} }
  if (to.name === 'login' && token) return { name: 'dashboard' }
  if (to.meta.admin && localStorage.getItem('role') !== 'admin') return { name: 'dashboard' }
})

export default router
