<template>
  <Teleport to="body">
    <transition-group name="toast" tag="div" class="fixed top-4 right-4 z-50 space-y-2">
      <div v-for="t in toasts" :key="t.id"
        class="flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg border backdrop-blur-sm min-w-[280px] max-w-sm animate-slide-in"
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
  </Teleport>
</template>

<script setup>
import { ref } from 'vue'

const toasts = ref([])
let nextId = 0

function show(msg, ok = true) {
  const id = nextId++
  toasts.value.push({ id, msg, ok })
  setTimeout(() => { toasts.value = toasts.value.filter(t => t.id !== id) }, 3000)
}

defineExpose({ show })
</script>

<style>
.toast-enter-active { animation: slideIn 0.3s ease; }
.toast-leave-active { animation: slideOut 0.3s ease; }
@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
@keyframes slideOut { from { transform: translateX(0); opacity: 1; } to { transform: translateX(100%); opacity: 0; } }
</style>
