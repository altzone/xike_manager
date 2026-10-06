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
    <router-view v-if="switchId" :switch-id="switchId" :key="switchId" />
  </div>
</template>

<script setup>
import { computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../composables/useApi.js'
import { useSwitchesStore } from '../stores/switches.js'
import { useI18n } from '../i18n/index.js'
import Icon from '../components/ui/Icon.vue'
import Btn from '../components/ui/Btn.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const sw = useSwitchesStore()
// null for anything that is not a positive integer (/switch/abc), so nothing polls /api/switches/NaN
const switchId = computed(() => {
  const id = Number(route.params.id)
  return Number.isInteger(id) && id > 0 ? id : null
})
let timer = null
let alive = true

async function loadInfo() {
  const id = switchId.value
  if (!id) return
  try {
    const info = await api(`/api/switches/${id}/info`)
    if (!alive) return
    if (!sw.list.some(s => s.id === info.id)) sw.list.push(info)
    else sw.patch(info.id, info)
  } catch (e) {
    if (e?.status === 404 && alive && id === switchId.value) router.replace('/')  // deleted switch
  }
}

// A ping for an unreachable switch can take several seconds: capture the id before the await and
// drop results that come back for another switch or after unmount, so they never overwrite the current status.
async function checkOnline() {
  const id = switchId.value
  if (!id) return
  let next
  try {
    const res = await api(`/api/switches/${id}/ping`)
    next = { online: !!res.online, temperature: res.temperature || '', error: res.error || '', checked: true }
  } catch (e) {
    next = { online: false, temperature: '', error: e.message, checked: true }
  }
  if (!alive || id !== switchId.value || sw.currentId !== id) return
  sw.status = next
}

function start() {
  clearInterval(timer)
  if (!switchId.value) {
    // leaving /switch/* clears the id too: only redirect while still on a switch route
    if (route.params.id !== undefined) router.replace('/')
    return
  }
  sw.setCurrent(switchId.value)
  loadInfo()
  checkOnline()
  timer = setInterval(checkOnline, 10000)
}

onMounted(start)
watch(switchId, start)
onUnmounted(() => { alive = false; clearInterval(timer); sw.setCurrent(null) })
</script>
