<template>
  <Teleport to="body">
    <transition name="fade">
      <div v-if="open" class="fixed inset-0 z-[90] bg-black/50 backdrop-blur-[2px]" @click="dismissible && $emit('close')"></div>
    </transition>
    <transition name="pop">
      <div v-if="open" class="fixed inset-0 z-[91] flex items-center justify-center p-4 pointer-events-none">
        <div class="card w-full pointer-events-auto flex flex-col max-h-[90vh]" :class="widths[width]" role="dialog" aria-modal="true" :aria-labelledby="id">
          <div class="flex items-start justify-between gap-4 px-5 pt-5 pb-3">
            <div class="min-w-0">
              <h2 :id="id" class="text-base font-semibold text-ink">{{ title }}</h2>
              <p v-if="subtitle" class="hint mt-0.5">{{ subtitle }}</p>
            </div>
            <Btn variant="ghost" size="sm" icon="x" icon-only :aria-label="t('common.close')" @click="$emit('close')" />
          </div>
          <div class="px-5 pb-5 overflow-y-auto"><slot /></div>
          <div v-if="$slots.footer" class="px-5 py-4 border-t border-line flex justify-end gap-2 bg-surface-2 rounded-b-[var(--radius-card)]">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { onMounted, onUnmounted, watch, nextTick } from 'vue'
import Btn from './Btn.vue'
import { useI18n } from '../../i18n/index.js'

const props = defineProps({
  open: Boolean,
  title: String,
  subtitle: String,
  width: { type: String, default: 'md' }, // sm | md | lg | xl
  dismissible: { type: Boolean, default: true },
})
const emit = defineEmits(['close'])
const { t } = useI18n()
const id = `modal-${Math.random().toString(36).slice(2, 8)}`
const widths = { sm: 'max-w-sm', md: 'max-w-md', lg: 'max-w-2xl', xl: 'max-w-4xl' }

function onKey(e) { if (e.key === 'Escape' && props.open && props.dismissible) emit('close') }
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
watch(() => props.open, async (v) => {
  if (!v) return
  await nextTick()
  document.querySelector('[role="dialog"] [autofocus], [role="dialog"] input, [role="dialog"] select, [role="dialog"] button')?.focus()
})
</script>
