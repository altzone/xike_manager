<template>
  <div class="space-y-5">
    <!-- Stats -->
    <p v-if="loadError && ports.length" role="alert" class="text-sm text-danger-ink bg-danger-soft border border-danger/30 rounded-lg px-3 py-2">{{ t('common.failedLoad') }} · {{ loadError }}</p>
    <div v-if="loadError && !ports.length" class="card">
      <EmptyState compact icon="x-circle" :title="t('common.failedLoad')" :text="loadError"><Btn size="sm" icon="refresh" @click="load">{{ t('ui.retry') }}</Btn></EmptyState>
    </div>
    <div v-else class="grid grid-cols-2 lg:grid-cols-5 gap-3">
      <Stat icon="fire" :label="t('swdash.temperature')" :value="temp" unit="°C" :tone="Number(temp) > 60 ? 'danger' : Number(temp) > 50 ? 'warn' : 'ok'" />
      <Stat icon="bolt" :label="t('swdash.portsUp')" :value="portsUp" unit="/ 10" tone="accent" />
      <Stat icon="arrow-up" :label="t('swdash.totalTx')" :value="fmt(totalTx)" tone="info" />
      <Stat icon="arrow-down" :label="t('swdash.totalRx')" :value="fmt(totalRx)" tone="sfp" />
      <Stat icon="warning" :label="t('swdash.errors')" :value="fmt(totalErrors)" :tone="totalErrors > 0 ? 'warn' : 'neutral'" class="col-span-2 lg:col-span-1" />
    </div>

    <!-- Faceplate + details -->
    <div class="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-5">
      <div class="space-y-3 min-w-0">
        <div class="flex items-center justify-between">
          <p class="eyebrow">{{ t('swdash.frontPanel') }}</p>
          <span class="flex items-center gap-1.5 text-xs" :class="sse.connected.value ? 'text-ok' : switchError ? 'text-danger' : 'text-muted'">
            <span class="dot" :class="sse.connected.value ? 'bg-ok live-dot' : switchError ? 'bg-danger' : 'bg-faint'"></span>{{ sse.connected.value ? t('ui.live') : switchError ? t('ui.offline') : t('ui.connecting') }}
          </span>
        </div>
        <Faceplate :ports="ports" :settings="settings" :selected="selected" :live="sse.connected.value" :model="model" :firmware="firmware" @select="selected = selected === $event ? null : $event" />
      </div>

      <div class="card">
        <div class="card-head"><div><h3 class="h2">{{ t('swdash.portDetails') }}</h3></div>
          <Badge v-if="sel" :tone="sel.port >= 9 ? 'sfp' : 'rj45'"><bdi dir="ltr">{{ sel.port >= 9 ? 'SFP+' : 'RJ45' }}</bdi></Badge>
        </div>
        <div v-if="sel" class="card-body space-y-3 text-sm">
          <div class="flex items-baseline justify-between">
            <span class="text-2xl font-semibold">{{ t('ports.port') }} {{ sel.port }}</span>
            <Badge :tone="isUp(sel) ? 'ok' : 'neutral'" dot>{{ isUp(sel) ? sel.link : t('ports.down') }}</Badge>
          </div>
          <p v-if="selSetting?.description" class="text-ink-2">{{ selSetting.description }}</p>
          <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
            <dt class="text-muted">{{ t('ports.status') }}</dt><dd class="text-end"><Badge :tone="selSetting?.status === 'Enabled' ? 'ok' : 'danger'">{{ selSetting?.status === 'Enabled' ? t('ports.enabled') : t('ports.disabled') }}</Badge></dd>
            <dt class="text-muted">{{ t('ports.speed') }}</dt><dd class="text-end mono">{{ selSetting?.speed_config || '—' }}</dd>
            <dt class="text-muted">{{ t('ports.flow') }}</dt><dd class="text-end mono">{{ selSetting?.flow_ctrl_config || '—' }}</dd>
            <dt class="text-muted">{{ t('ports.tx') }}</dt><dd class="text-end num">{{ (sel.tx_good || 0).toLocaleString(locale) }} <bdi dir="ltr" class="text-ok" v-if="sel.tx_pps">+{{ sel.tx_pps }}/s</bdi></dd>
            <dt class="text-muted">{{ t('ports.rx') }}</dt><dd class="text-end num">{{ (sel.rx_good || 0).toLocaleString(locale) }} <bdi dir="ltr" class="text-ok" v-if="sel.rx_pps">+{{ sel.rx_pps }}/s</bdi></dd>
            <dt class="text-muted">{{ t('ports.errors') }}</dt><dd class="text-end num" :class="(sel.tx_bad || 0) + (sel.rx_bad || 0) > 0 ? 'text-danger' : ''">{{ ((sel.tx_bad || 0) + (sel.rx_bad || 0)).toLocaleString(locale) }}</dd>
          </dl>
          <Btn tag="router-link" :to="`/switch/${switchId}/ports`" size="sm" icon="ports" block>{{ t('swdash.openPorts') }}</Btn>
        </div>
        <EmptyState v-else compact icon="ports" :title="t('swdash.selectPort')" />
      </div>
    </div>

    <!-- Recent changes -->
    <div class="card">
      <div class="card-head">
        <div><h3 class="h2">{{ t('swdash.recentChanges') }}</h3><p class="hint">{{ t('sys.changesDesc') }}</p></div>
        <Btn tag="router-link" :to="`/switch/${switchId}/system#changes`" variant="link" size="sm">{{ t('ui.viewAll') }}</Btn>
      </div>
      <EmptyState v-if="changesError" compact icon="x-circle" :title="t('common.failedLoad')" :text="changesError"><Btn size="sm" icon="refresh" @click="load">{{ t('ui.retry') }}</Btn></EmptyState>
      <ul v-else-if="changes.length" class="divide-y divide-line">
        <li v-for="c in changes" :key="c.id" class="px-5 py-2.5 flex items-center gap-3 text-sm">
          <span class="w-7 h-7 rounded-md bg-surface-3 text-muted flex items-center justify-center shrink-0"><Icon :name="changeIcon(c.action)" :size="15" /></span>
          <span class="flex-1 min-w-0 truncate"><span class="text-ink">{{ t('changes.' + c.action) }}</span><span class="text-muted"> · {{ c.username || '?' }}</span></span>
          <span class="text-xs text-muted shrink-0 num">{{ fmtDate(c.created_at) }}</span>
        </li>
      </ul>
      <EmptyState v-else-if="loaded" compact icon="history" :title="t('swdash.noChanges')" />
      <p v-else class="px-5 py-6 text-center text-sm text-muted">{{ t('common.loading') }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useSSE } from '../composables/useSSE.js'
import { api } from '../composables/useApi.js'
import { useI18n } from '../i18n/index.js'
import { useSwitchesStore } from '../stores/switches.js'
import Stat from '../components/ui/Stat.vue'
import Badge from '../components/ui/Badge.vue'
import Btn from '../components/ui/Btn.vue'
import Icon from '../components/ui/Icon.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import Faceplate from '../components/Faceplate.vue'

const props = defineProps({ switchId: Number })
const { t, locale } = useI18n()
const sw = useSwitchesStore()
const sse = useSSE(props.switchId)
const status = ref({})
const initialStats = ref([])
const initialSettings = ref([])
const changes = ref([])
const selected = ref(null)
const loaded = ref(false)
const loadError = ref('')
const changesError = ref('')

const temp = computed(() => sse.data.value?.temperature || status.value?.temperature || '—')
const ports = computed(() => sse.data.value?.ports || initialStats.value)
// the stream's port_settings carry no description (stored in the DB, only GET /ports adds it): merge it in
const descByPort = computed(() => Object.fromEntries(initialSettings.value.map(s => [s.port, s.description])))
const settings = computed(() => {
  const live = sse.data.value?.port_settings
  if (!live) return initialSettings.value
  return live.map(s => ({ ...s, description: s.description ?? descByPort.value[s.port] }))
})
const switchError = computed(() => sse.switchError?.value || null)
const model = computed(() => status.value?.modle || sw.current?.model || '')
const firmware = computed(() => status.value?.fw_ver || sw.current?.firmware || '')
const portsUp = computed(() => ports.value.filter(isUp).length)
const totalTx = computed(() => ports.value.reduce((s, p) => s + (p.tx_good || 0), 0))
const totalRx = computed(() => ports.value.reduce((s, p) => s + (p.rx_good || 0), 0))
const totalErrors = computed(() => ports.value.reduce((s, p) => s + (p.tx_bad || 0) + (p.rx_bad || 0), 0))
const sel = computed(() => ports.value.find(p => p.port === selected.value) || (selected.value ? { port: selected.value, link: '' } : null))
const selSetting = computed(() => settings.value.find(p => p.port === selected.value))

function isUp(p) { return !!p.link && p.link !== 'Link Down' }
function fmt(n) {
  if (!n) return '0'
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'G'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}
function fmtDate(d) { return d ? new Date(d + 'Z').toLocaleString(locale.value, { dateStyle: 'short', timeStyle: 'short' }) : '' }
const ICONS = { ports: 'ports', vlans: 'vlans', lag: 'lag', mirror: 'mirror', loop: 'loop', stp: 'shield', storm: 'bolt', igmp: 'activity', eee: 'bolt', time: 'clock', sntp: 'clock', network: 'network', reboot: 'power', static_mac_add: 'mac', static_mac_delete: 'mac', port_mapping: 'ports' }
function changeIcon(a) { return ICONS[a] || 'history' }

async function load() {
  const id = props.switchId
  loadError.value = ''
  try {
    status.value = await api(`/api/switches/${id}/status`)
    initialStats.value = await api(`/api/switches/${id}/ports/stats`)
    initialSettings.value = await api(`/api/switches/${id}/ports`)
  } catch (e) { loadError.value = e.message }
  try {
    changes.value = await api(`/api/switches/${id}/changes?limit=6`)
    changesError.value = ''
  } catch (e) { changesError.value = e.message }
  loaded.value = true
}

onMounted(() => {
  sse.connect()
  load()
})
</script>
