<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Toast notifications -->
    <div class="fixed top-4 right-4 z-[100] space-y-2">
      <transition-group name="toast">
        <div v-for="t in toast.toasts" :key="t.id"
          class="flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg border backdrop-blur-sm min-w-[280px] max-w-sm"
          :class="t.ok ? 'bg-emerald-50/95 border-emerald-200 text-emerald-800' : 'bg-red-50/95 border-red-200 text-red-800'">
          <svg v-if="t.ok" class="w-5 h-5 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
          </svg>
          <svg v-else class="w-5 h-5 text-red-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
          </svg>
          <span class="text-sm font-medium">{{ t.msg }}</span>
        </div>
      </transition-group>
    </div>

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
        <!-- Language selector -->
        <div class="relative" ref="langDropdown">
          <button @click="showLang = !showLang" class="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition px-2 py-1 rounded-lg hover:bg-gray-100">
            <span>{{ currentLang?.flag }}</span>
            <span class="hidden sm:inline">{{ currentLang?.name }}</span>
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
          </button>
          <div v-if="showLang" class="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-xl shadow-xl py-1 w-48 z-50 max-h-80 overflow-auto">
            <button v-for="lang in i18n.LANGUAGES" :key="lang.code" @click="i18n.setLocale(lang.code); showLang = false"
              class="w-full px-3 py-2 text-left text-sm flex items-center gap-2 hover:bg-gray-50 transition"
              :class="lang.code === i18n.locale.value ? 'bg-indigo-50 text-indigo-700' : 'text-gray-700'">
              <span>{{ lang.flag }}</span>
              <span>{{ lang.name }}</span>
            </button>
          </div>
        </div>
        <span class="text-sm text-gray-500">{{ auth.username }}</span>
        <button @click="doLogout" class="text-sm text-gray-400 hover:text-red-500 transition">{{ i18n.t('nav.logout') }}</button>
      </div>
    </nav>
    <router-view />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useToast } from '../composables/useToast.js'
import { useI18n } from '../i18n/index.js'

const router = useRouter()
const showLang = ref(false)
const auth = useAuthStore()
const toast = useToast()
const i18n = useI18n()
const currentLang = computed(() => i18n.LANGUAGES.find(l => l.code === i18n.locale.value))

function doLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style>
.toast-enter-active { animation: toastIn 0.3s ease; }
.toast-leave-active { animation: toastOut 0.25s ease; }
@keyframes toastIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
@keyframes toastOut { from { opacity: 1; } to { opacity: 0; transform: translateY(-10px); } }
</style>
