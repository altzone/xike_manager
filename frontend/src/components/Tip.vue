<template>
  <span class="inline-flex items-center cursor-help" ref="iconEl" @mouseenter="open" @mouseleave="show = false">
    <svg class="w-4 h-4 text-indigo-400 hover:text-indigo-600 transition-colors" fill="currentColor" viewBox="0 0 20 20">
      <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clip-rule="evenodd"/>
    </svg>
    <Teleport to="body">
      <transition name="tip">
        <div v-if="show" class="fixed px-3.5 py-2.5 bg-gray-900 text-white text-xs rounded-xl shadow-2xl w-72 leading-relaxed pointer-events-none" :style="{ top: pos.y + 'px', left: pos.x + 'px', zIndex: 99999 }">
          <span class="font-semibold block mb-0.5 text-indigo-300" v-if="title">{{ title }}</span>
          <slot>{{ text }}</slot>
        </div>
      </transition>
    </Teleport>
  </span>
</template>

<script setup>
import { ref, reactive } from 'vue'

defineProps({ text: String, title: String })
const show = ref(false)
const iconEl = ref(null)
const pos = reactive({ x: 0, y: 0 })

function open() {
  if (!iconEl.value) return
  const rect = iconEl.value.getBoundingClientRect()
  let x = rect.left + rect.width / 2 - 144 // 144 = half of w-72 (288/2)
  let y = rect.top - 8
  // Will position above, then shift down in nextTick after render
  // For now estimate ~60px tooltip height
  y = rect.top - 68
  if (y < 4) y = rect.bottom + 8
  if (x < 4) x = 4
  if (x + 288 > window.innerWidth - 4) x = window.innerWidth - 292
  pos.x = x
  pos.y = y
  show.value = true
}
</script>

<style>
.tip-enter-active { transition: opacity 0.15s, transform 0.15s; }
.tip-leave-active { transition: opacity 0.1s; }
.tip-enter-from { opacity: 0; transform: translateY(4px); }
.tip-leave-to { opacity: 0; }
</style>
