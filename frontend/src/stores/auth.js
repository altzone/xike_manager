import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../composables/useApi.js'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref(localStorage.getItem('username') || '')
  const role = ref(localStorage.getItem('role') || '')

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => role.value === 'admin')

  async function login(user, pass) {
    const res = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username: user, password: pass }) })
    token.value = res.token
    username.value = res.username
    role.value = res.role
    localStorage.setItem('token', res.token)
    localStorage.setItem('username', res.username)
    localStorage.setItem('role', res.role)
  }

  // the role stored at login can go stale (demotion): re-read it from the server
  async function refresh() {
    if (!token.value) return
    try {
      const me = await api('/api/auth/me')
      username.value = me.username
      role.value = me.role
      localStorage.setItem('username', me.username)
      localStorage.setItem('role', me.role)
    } catch (e) {}
  }

  function logout() {
    token.value = ''
    username.value = ''
    role.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    localStorage.removeItem('role')
  }

  return { token, username, role, isLoggedIn, isAdmin, login, refresh, logout }
})
