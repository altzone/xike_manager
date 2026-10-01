<template>
  <span class="chip" :class="tones[tone]">
    <span v-if="dot" class="dot" :class="dots[tone]"></span>
    <slot />
  </span>
</template>

<script setup>
defineProps({
  tone: { type: String, default: 'neutral' }, // neutral | accent | ok | warn | danger | info | rj45 | sfp
  dot: Boolean,
})
const tones = {
  neutral: 'bg-surface-3 text-ink-2',
  accent: 'bg-accent-soft text-accent-ink',
  ok: 'bg-ok-soft text-ok-ink',
  warn: 'bg-warn-soft text-warn-ink',
  danger: 'bg-danger-soft text-danger-ink',
  info: 'bg-info-soft text-info-ink',
  rj45: 'bg-rj45-soft text-rj45',
  sfp: 'bg-sfp-soft text-sfp',
}
const dots = {
  neutral: 'bg-faint', accent: 'bg-accent', ok: 'bg-ok', warn: 'bg-warn', danger: 'bg-danger', info: 'bg-info', rj45: 'bg-rj45', sfp: 'bg-sfp',
}
</script>
