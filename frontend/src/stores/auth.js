import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api, storageGet, storageSet, storageRemove } from '../composables/useApi.js'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(storageGet('token') || '')
  const username = ref(storageGet('username') || '')
  const role = ref(storageGet('role') || '')

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => role.value === 'admin')

  async function login(user, pass) {
    const res = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username: user, password: pass }) })
    token.value = res.token
    username.value = res.username
    role.value = res.role
    storageSet('token', res.token)
    storageSet('username', res.username)
    storageSet('role', res.role)
  }

  // the role stored at login can go stale (demotion): re-read it from the server
  async function refresh() {
    if (!token.value) return
    try {
      const me = await api('/api/auth/me')
      username.value = me.username
      role.value = me.role
      storageSet('username', me.username)
      storageSet('role', me.role)
    } catch (e) {}
  }

  function logout() {
    token.value = ''
    username.value = ''
    role.value = ''
    storageRemove('token')
    storageRemove('username')
    storageRemove('role')
  }

  return { token, username, role, isLoggedIn, isAdmin, login, refresh, logout }
})
