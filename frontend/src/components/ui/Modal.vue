<template>
  <Teleport to="body">
    <transition name="fade">
      <div v-if="open" class="fixed inset-0 bg-black/50 backdrop-blur-[2px]" :style="{ zIndex: layer }" @click="dismissible && $emit('close')"></div>
    </transition>
    <transition name="pop">
      <div v-if="open" class="fixed inset-0 flex items-center justify-center p-4 pointer-events-none" :style="{ zIndex: layer + 1 }">
        <div ref="root" class="card w-full pointer-events-auto flex flex-col max-h-[90vh]" :class="widths[width]" role="dialog" aria-modal="true" :aria-labelledby="id">
          <div class="flex items-start justify-between gap-4 px-5 pt-5 pb-3">
            <div class="min-w-0">
              <h2 :id="id" class="text-base font-semibold text-ink">{{ title }}</h2>
              <p v-if="subtitle" class="hint mt-0.5">{{ subtitle }}</p>
            </div>
            <Btn variant="ghost" size="sm" icon="x" icon-only :aria-label="t('common.close')" data-modal-close @click="$emit('close')" />
          </div>
          <div class="px-5 pb-5 overflow-y-auto"><slot /></div>
          <div v-if="$slots.footer" class="px-5 py-4 border-t border-line flex justify-end gap-2 bg-surface-2 rounded-b-[var(--radius-card)]" data-modal-footer>
            <slot name="footer" />
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import Btn from './Btn.vue'
import { useI18n } from '../../i18n/index.js'

const props = defineProps({
  open: Boolean,
  title: String,
  subtitle: String,
  width: { type: String, default: 'md' }, // sm | md | lg | xl
  dismissible: { type: Boolean, default: true },
  // z-index of the overlay; the global ConfirmDialog uses a higher layer so it paints above page modals
  layer: { type: Number, default: 90 },
})
const emit = defineEmits(['close'])
const { t } = useI18n()
const id = `modal-${Math.random().toString(36).slice(2, 8)}`
const widths = { sm: 'max-w-sm', md: 'max-w-md', lg: 'max-w-2xl', xl: 'max-w-4xl' }
const root = ref(null)
let opener = null // element focused before the dialog opened, restored on close
// only the topmost open dialog reacts to Escape and traps Tab
function isTop() { return stack[stack.length - 1] === id }

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function focusables() {
  return root.value ? [...root.value.querySelectorAll(FOCUSABLE)].filter(el => el.offsetParent !== null || el === document.activeElement) : []
}

function onKey(e) {
  if (!props.open || !isTop()) return
  if (e.key === 'Escape') {
    if (props.dismissible) { e.preventDefault(); emit('close') }
    return
  }
  if (e.key !== 'Tab') return
  // keep Tab / Shift+Tab inside the dialog
  const els = focusables()
  if (!els.length) { e.preventDefault(); return }
  const first = els[0], last = els[els.length - 1]
  const inside = root.value?.contains(document.activeElement)
  if (e.shiftKey && (document.activeElement === first || !inside)) { e.preventDefault(); last.focus() }
  else if (!e.shiftKey && (document.activeElement === last || !inside)) { e.preventDefault(); first.focus() }
}

onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => { document.removeEventListener('keydown', onKey); release() })

watch(() => props.open, async (v) => {
  if (!v) { release(); return }
  opener = document.activeElement
  stack.push(id)
  await nextTick()
  const el = root.value
  if (!el) return
  // prefer an explicit autofocus, then the first field, then a footer action — never the header close button
  const target = el.querySelector('[autofocus]')
    || el.querySelector('input:not([disabled]), select:not([disabled]), textarea:not([disabled])')
    || el.querySelector('[data-modal-footer] button:not([disabled])')
    || el.querySelector(`${FOCUSABLE}:not([data-modal-close])`)
    || el.querySelector('[data-modal-close]')
  target?.focus()
})

function release() {
  const i = stack.lastIndexOf(id)
  if (i === -1) return
  stack.splice(i, 1)
  const back = opener
  opener = null
  if (back && typeof back.focus === 'function' && document.contains(back)) back.focus()
}
</script>

<script>
// Open dialogs, bottom to top (shared by every Modal instance)
const stack = []
</script>
