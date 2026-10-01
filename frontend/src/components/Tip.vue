<template>
  <button type="button" class="inline-flex items-center align-middle bg-transparent border-0 p-0 cursor-help" ref="iconEl"
    @mouseenter="open" @mouseleave="close" @focus="open" @blur="close" @keydown.esc="close"
    :aria-label="title || text" :aria-describedby="show ? id : undefined">
    <Icon name="question" :size="15" class="text-faint hover:text-accent transition-colors" />
    <Teleport to="body">
      <transition name="fade">
        <div v-if="show" :id="id" role="tooltip" class="fixed w-72 px-3.5 py-2.5 rounded-xl text-xs leading-relaxed bg-side text-side-ink shadow-[var(--shadow-pop)] pointer-events-none"
          :style="{ top: pos.y + 'px', left: pos.x + 'px', zIndex: 99999 }">
          <span v-if="title" class="block mb-0.5 font-semibold text-accent-ink dark:text-accent">{{ title }}</span>
          <slot>{{ text }}</slot>
        </div>
      </transition>
    </Teleport>
  </button>
</template>

<script setup>
import { ref, reactive, onUnmounted } from 'vue'
import Icon from './ui/Icon.vue'

defineProps({ text: String, title: String })
const show = ref(false)
const iconEl = ref(null)
const pos = reactive({ x: 0, y: 0 })
const id = `tip-${Math.random().toString(36).slice(2, 8)}`

// Escape dismisses the tooltip even when it was opened by hover (WCAG 1.4.13)
function onDocKey(e) { if (e.key === 'Escape') close() }

function open() {
  if (!iconEl.value) return
  const rect = iconEl.value.getBoundingClientRect()
  let x = rect.left + rect.width / 2 - 144
  let y = rect.top - 76
  if (y < 4) y = rect.bottom + 8
  if (x < 4) x = 4
  if (x + 288 > window.innerWidth - 4) x = window.innerWidth - 292
  pos.x = x; pos.y = y
  if (!show.value) document.addEventListener('keydown', onDocKey)
  show.value = true
}
function close() {
  if (show.value) document.removeEventListener('keydown', onDocKey)
  show.value = false
}
onUnmounted(close)
</script>
