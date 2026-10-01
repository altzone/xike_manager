<template>
  <div class="flex flex-col items-center justify-center text-center px-6" :class="compact ? 'py-8' : 'py-14'">
    <div class="w-12 h-12 rounded-xl bg-surface-3 text-muted flex items-center justify-center mb-3">
      <Icon :name="icon" :size="22" />
    </div>
    <p class="text-sm font-medium text-ink">{{ title }}</p>
    <p v-if="text" class="hint mt-1 max-w-sm">{{ text }}</p>
    <div v-if="$slots.default" class="mt-4"><slot /></div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
defineProps({ icon: { type: String, default: 'info' }, title: String, text: String, compact: Boolean })
</script>
