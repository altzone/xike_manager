<template>
  <component :is="tag" :type="tag === 'button' ? type : undefined" :disabled="disabled || loading"
    :class="[base, variants[variant], sizes[size], block ? 'w-full' : '', iconOnly ? iconSizes[size] : '']"
    :aria-label="ariaLabel" :title="title">
    <svg v-if="loading" class="animate-spin shrink-0" :width="iconPx" :height="iconPx" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" class="opacity-25"/>
      <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
    </svg>
    <Icon v-else-if="icon" :name="icon" :size="iconPx" />
    <slot />
  </component>
</template>

<script setup>
import { computed } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({
  variant: { type: String, default: 'secondary' }, // primary | secondary | ghost | danger | danger-soft | link
  size: { type: String, default: 'md' },           // xs | sm | md | lg
  type: { type: String, default: 'button' },
  tag: { type: String, default: 'button' },
  icon: String,
  iconOnly: Boolean,
  loading: Boolean,
  disabled: Boolean,
  block: Boolean,
  ariaLabel: String,
  title: String,
})

const base = 'inline-flex items-center justify-center gap-1.5 font-medium rounded-lg border transition-colors duration-150 select-none whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2'
const variants = {
  primary: 'bg-accent border-accent text-white hover:bg-accent-hover hover:border-accent-hover shadow-sm',
  secondary: 'bg-surface border-line-strong text-ink-2 hover:bg-surface-2 hover:text-ink',
  ghost: 'bg-transparent border-transparent text-muted hover:bg-surface-3 hover:text-ink',
  danger: 'bg-danger border-danger text-white hover:opacity-90',
  'danger-soft': 'bg-danger-soft border-transparent text-danger-ink hover:bg-danger hover:text-white',
  link: 'bg-transparent border-transparent text-accent hover:underline px-0',
}
const sizes = { xs: 'text-[11.5px] h-7 px-2', sm: 'text-xs h-8 px-2.5', md: 'text-[13px] h-9 px-3.5', lg: 'text-sm h-10 px-4' }
const iconSizes = { xs: 'w-7 px-0', sm: 'w-8 px-0', md: 'w-9 px-0', lg: 'w-10 px-0' }
const iconPx = computed(() => ({ xs: 14, sm: 15, md: 16, lg: 18 }[props.size]))
</script>
