<template>
  <div class="min-h-screen flex flex-col bg-side text-side-ink">
    <div class="flex items-center justify-end gap-1 p-3">
      <Btn variant="ghost" :icon="themeIcon" icon-only :aria-label="t('ui.theme')" class="text-side-muted hover:text-white hover:bg-side-2" @click="cycle" />
      <div class="relative" ref="langRef" @keydown.escape="showLang = false">
        <Btn variant="ghost" class="text-side-muted hover:text-white hover:bg-side-2" :aria-label="t('ui.language')" aria-haspopup="menu" :aria-expanded="showLang" @click="showLang = !showLang">
          <span class="text-base leading-none">{{ currentLang?.flag }}</span><span class="text-xs">{{ currentLang?.name }}</span><Icon name="chevron-down" :size="14" />
        </Btn>
        <transition name="pop">
          <div v-if="showLang" role="menu" :aria-label="t('ui.language')" class="absolute end-0 top-full mt-1 w-48 card py-1 max-h-80 overflow-auto z-50 shadow-[var(--shadow-pop)] text-ink">
            <button v-for="lang in i18n.LANGUAGES" :key="lang.code" role="menuitemradio" :aria-checked="lang.code === i18n.locale.value" @click="i18n.setLocale(lang.code); showLang = false"
              class="w-full px-3 py-2 text-start text-sm flex items-center gap-2.5 hover:bg-surface-2 transition" :class="lang.code === i18n.locale.value ? 'text-accent font-medium' : 'text-ink-2'">
              <span class="text-base leading-none">{{ lang.flag }}</span><span class="flex-1">{{ lang.name }}</span>
            </button>
          </div>
        </transition>
      </div>
    </div>
    <div class="flex-1 flex items-center justify-center p-4 pb-16">
      <div class="w-full max-w-sm">
        <div class="flex flex-col items-center text-center mb-6">
          <img src="/switch.svg" alt="" class="w-14 h-14 mb-4 drop-shadow-lg" />
          <h1 class="text-2xl font-semibold tracking-tight text-white">{{ title }}</h1>
          <p class="text-side-muted mt-1 text-sm">{{ subtitle }}</p>
        </div>
        <div class="card p-6 text-ink"><slot /></div>
        <p class="text-center text-[11px] text-side-muted mt-6">{{ t('auth.footer') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../i18n/index.js'
import { useTheme } from '../composables/useTheme.js'
import Btn from './ui/Btn.vue'
import Icon from './ui/Icon.vue'

defineProps({ title: String, subtitle: String })
const i18n = useI18n()
const { t } = i18n
const { theme, cycle } = useTheme()
const showLang = ref(false)
const langRef = ref(null)
const currentLang = computed(() => i18n.LANGUAGES.find(l => l.code === i18n.locale.value))
const themeIcon = computed(() => ({ light: 'sun', dark: 'moon', system: 'monitor' }[theme.value]))
function onDoc(e) { if (langRef.value && !langRef.value.contains(e.target)) showLang.value = false }
onMounted(() => document.addEventListener('click', onDoc))
onUnmounted(() => document.removeEventListener('click', onDoc))
</script>
