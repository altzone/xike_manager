<template>
  <button type="button" role="switch" :aria-checked="modelValue" :aria-label="label" :disabled="disabled"
    @click="$emit('update:modelValue', !modelValue)"
    class="relative inline-flex shrink-0 items-center rounded-full border border-transparent transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
    :class="[sizes[size].track, modelValue ? 'bg-ok' : 'bg-line-strong']">
    <span class="pointer-events-none inline-block rounded-full bg-white shadow transition-transform duration-200"
      :class="[sizes[size].knob, modelValue ? sizes[size].on : 'translate-x-0.5 rtl:-translate-x-0.5']"></span>
  </button>
</template>

<script setup>
defineProps({
  modelValue: Boolean,
  label: String,
  disabled: Boolean,
  size: { type: String, default: 'md' },
})
defineEmits(['update:modelValue'])
const sizes = {
  sm: { track: 'h-5 w-9', knob: 'h-4 w-4', on: 'translate-x-[18px] rtl:-translate-x-[18px]' },
  md: { track: 'h-6 w-11', knob: 'h-5 w-5', on: 'translate-x-[22px] rtl:-translate-x-[22px]' },
}
</script>
