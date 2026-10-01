<template>
  <div class="space-y-5">
    <div v-if="sw.status.checked && sw.status.online === false" class="rounded-xl border border-danger/40 bg-danger-soft px-4 py-3 flex items-start gap-3 text-sm text-danger-ink">
      <Icon name="warning" :size="18" class="mt-0.5 shrink-0" />
      <div class="flex-1">
        <p class="font-medium">{{ t('sw.unreachable') }}</p>
        <p v-if="sw.status.error" class="text-xs opacity-80 mt-0.5 mono">{{ sw.status.error }}</p>
      </div>
      <Btn size="sm" icon="refresh" @click="checkOnline">{{ t('ui.retry') }}</Btn>
    </div>
    <router-view :switch-id="switchId" :key="switchId" />
  </div>
</template>

<script setup>
import { computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../composables/useApi.js'
import { useSwitchesStore } from '../stores/switches.js'
import { useI18n } from '../i18n/index.js'
import Icon from '../components/ui/Icon.vue'
import Btn from '../components/ui/Btn.vue'

const { t } = useI18n()
const route = useRoute()
const sw = useSwitchesStore()
const switchId = computed(() => parseInt(route.params.id))
let timer = null

async function loadInfo() {
  try {
    const info = await api(`/api/switches/${switchId.value}/info`)
    if (!sw.list.some(s => s.id === info.id)) sw.list.push(info)
    else sw.patch(info.id, info)
  } catch (e) {}
}

async function checkOnline() {
  try {
    const res = await api(`/api/switches/${switchId.value}/ping`)
    sw.status = { online: !!res.online, temperature: res.temperature || '', error: res.error || '', checked: true }
  } catch (e) {
    sw.status = { online: false, temperature: '', error: e.message, checked: true }
  }
}

function start() {
  sw.setCurrent(switchId.value)
  loadInfo()
  checkOnline()
  clearInterval(timer)
  timer = setInterval(checkOnline, 10000)
}

onMounted(start)
watch(switchId, start)
onUnmounted(() => { clearInterval(timer); sw.setCurrent(null) })
</script>
