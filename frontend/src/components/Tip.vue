<template>
  <span class="relative inline-flex items-center group cursor-help">
    <svg class="w-3.5 h-3.5 text-gray-300 hover:text-indigo-500 transition" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
    </svg>
    <span class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 w-64 leading-relaxed z-50 pointer-events-none">
      <span class="font-semibold block mb-0.5" v-if="title">{{ title }}</span>
      <slot>{{ text }}</slot>
      <span class="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"></span>
    </span>
  </span>
</template>

<script setup>
defineProps({ text: String, title: String })
</script>
