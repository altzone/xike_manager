<template>
  <span class="inline-flex items-center align-middle" ref="iconEl" @mouseenter="open" @mouseleave="show = false" @focusin="open" @focusout="show = false" tabindex="0" :aria-label="title || text">
    <Icon name="question" :size="15" class="text-faint hover:text-accent transition-colors cursor-help" />
    <Teleport to="body">
      <transition name="fade">
        <div v-if="show" role="tooltip" class="fixed w-72 px-3.5 py-2.5 rounded-xl text-xs leading-relaxed bg-side text-side-ink shadow-[var(--shadow-pop)] pointer-events-none"
          :style="{ top: pos.y + 'px', left: pos.x + 'px', zIndex: 99999 }">
          <span v-if="title" class="block mb-0.5 font-semibold text-accent-ink dark:text-accent">{{ title }}</span>
          <slot>{{ text }}</slot>
        </div>
      </transition>
    </Teleport>
  </span>
</template>

<script setup>
import { ref, reactive } from 'vue'
import Icon from './ui/Icon.vue'

defineProps({ text: String, title: String })
const show = ref(false)
const iconEl = ref(null)
const pos = reactive({ x: 0, y: 0 })

function open() {
  if (!iconEl.value) return
  const rect = iconEl.value.getBoundingClientRect()
  let x = rect.left + rect.width / 2 - 144
  let y = rect.top - 76
  if (y < 4) y = rect.bottom + 8
  if (x < 4) x = 4
  if (x + 288 > window.innerWidth - 4) x = window.innerWidth - 292
  pos.x = x; pos.y = y
  show.value = true
}
</script>
