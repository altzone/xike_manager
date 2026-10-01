<template>
  <div class="card px-4 py-3.5 flex items-center gap-3.5 min-w-0">
    <div class="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" :class="tones[tone]">
      <Icon :name="icon" :size="19" />
    </div>
    <div class="min-w-0">
      <p class="eyebrow leading-tight">{{ label }}</p>
      <p class="text-lg font-semibold text-ink leading-tight truncate num" :class="valueClass">
        <!-- value + unit are one LTR token ("3 / 10", "41 °C"), also under dir=rtl -->
        <bdi dir="ltr"><slot>{{ value }}</slot><span v-if="unit" class="text-xs font-normal text-muted ms-0.5">{{ unit }}</span></bdi>
      </p>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
defineProps({
  icon: { type: String, default: 'info' },
  label: String,
  value: [String, Number],
  unit: String,
  tone: { type: String, default: 'accent' },
  valueClass: String,
})
const tones = {
  accent: 'bg-accent-soft text-accent', ok: 'bg-ok-soft text-ok', warn: 'bg-warn-soft text-warn',
  danger: 'bg-danger-soft text-danger', info: 'bg-info-soft text-info', neutral: 'bg-surface-3 text-muted', sfp: 'bg-sfp-soft text-sfp',
}
</script>
