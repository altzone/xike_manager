<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Top bar -->
    <nav class="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
          <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01"/>
          </svg>
        </div>
        <router-link to="/" class="text-lg font-bold text-gray-900 hover:text-indigo-600 transition">SwitchPilot</router-link>
      </div>
      <div class="flex items-center gap-4">
        <span class="text-sm text-gray-500">{{ auth.username }}</span>
        <button @click="doLogout" class="text-sm text-gray-400 hover:text-red-500 transition">Logout</button>
      </div>
    </nav>
    <router-view />
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const auth = useAuthStore()

function doLogout() {
  auth.logout()
  router.push('/login')
}
</script>
