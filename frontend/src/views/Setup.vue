<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 to-slate-800">
    <div class="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md">
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-16 h-16 bg-emerald-600 rounded-xl mb-4">
          <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"/>
          </svg>
        </div>
        <h1 class="text-2xl font-bold text-gray-900">{{ t('setup.title') }}</h1>
        <p class="text-gray-500 mt-1">{{ t('setup.subtitle') }}</p>
      </div>
      <form @submit.prevent="doSetup" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('login.username') }}</label>
          <input v-model="username" type="text" required autofocus
            class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent outline-none"/>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('login.password') }}</label>
          <input v-model="password" type="password" required
            class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent outline-none"/>
        </div>
        <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>
        <button type="submit" :disabled="loading"
          class="w-full py-3 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 transition disabled:opacity-50">
          {{ loading ? t('setup.creating') : t('setup.create') }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../composables/useApi.js'
import { useI18n } from '../i18n/index.js'

const router = useRouter()
const { t } = useI18n()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function doSetup() {
  loading.value = true
  error.value = ''
  try {
    await api('/api/setup', { method: 'POST', body: JSON.stringify({ username: username.value, password: password.value }) })
    router.push('/login')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>
