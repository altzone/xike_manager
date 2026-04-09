import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/Login.vue') },
  { path: '/setup', name: 'setup', component: () => import('./views/Setup.vue') },
  {
    path: '/',
    component: () => import('./views/Layout.vue'),
    meta: { auth: true },
    children: [
      { path: '', name: 'dashboard', component: () => import('./views/Dashboard.vue') },
      { path: 'switch/:id', name: 'switch', component: () => import('./views/SwitchView.vue'),
        children: [
          { path: '', name: 'switch-dashboard', component: () => import('./views/SwitchDashboard.vue') },
          { path: 'ports', name: 'switch-ports', component: () => import('./views/Ports.vue') },
          { path: 'vlans', name: 'switch-vlans', component: () => import('./views/Vlans.vue') },
          { path: 'lag', name: 'switch-lag', component: () => import('./views/Lag.vue') },
          { path: 'monitoring', name: 'switch-monitoring', component: () => import('./views/Monitoring.vue') },
          { path: 'system', name: 'switch-system', component: () => import('./views/System.vue') },
        ]
      },
    ]
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  const token = localStorage.getItem('token')
  if (to.meta.auth && !token) return { name: 'login' }
  if (to.name === 'login' && token) return { name: 'dashboard' }
})

export default router
