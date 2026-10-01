<template>
  <div class="space-y-5">
    <!-- Stats -->
    <div class="grid grid-cols-2 lg:grid-cols-5 gap-3">
      <Stat icon="fire" :label="t('swdash.temperature')" :value="temp" unit="°C" :tone="Number(temp) > 60 ? 'danger' : Number(temp) > 50 ? 'warn' : 'ok'" />
      <Stat icon="bolt" :label="t('swdash.portsUp')" :value="portsUp" unit="/ 10" tone="accent" />
      <Stat icon="arrow-up" :label="t('swdash.totalTx')" :value="fmt(totalTx)" tone="info" />
      <Stat icon="arrow-down" :label="t('swdash.totalRx')" :value="fmt(totalRx)" tone="sfp" />
      <Stat icon="warning" :label="t('swdash.errors')" :value="fmt(totalErrors)" :tone="totalErrors > 0 ? 'warn' : 'neutral'" />
    </div>

    <!-- Faceplate + details -->
    <div class="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-5">
      <div class="space-y-3 min-w-0">
        <div class="flex items-center justify-between">
          <p class="eyebrow">{{ t('swdash.frontPanel') }}</p>
          <span class="flex items-center gap-1.5 text-xs" :class="sse.connected.value ? 'text-ok' : 'text-muted'">
            <span class="dot" :class="sse.connected.value ? 'bg-ok live-dot' : 'bg-faint'"></span>{{ sse.connected.value ? t('ui.live') : t('ui.connecting') }}
          </span>
        </div>
        <Faceplate :ports="ports" :settings="settings" :selected="selected" :live="sse.connected.value" :model="model" :firmware="firmware" @select="selected = selected === $event ? null : $event" />
      </div>

      <div class="card">
        <div class="card-head"><div><h3 class="h2">{{ t('swdash.portDetails') }}</h3></div>
          <Badge v-if="sel" :tone="sel.port >= 9 ? 'sfp' : 'rj45'">{{ sel.port >= 9 ? 'SFP+' : 'RJ45' }}</Badge>
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
            <dt class="text-muted">{{ t('ports.tx') }}</dt><dd class="text-end num">{{ (sel.tx_good || 0).toLocaleString(locale) }} <span class="text-ok" v-if="sel.tx_pps">+{{ sel.tx_pps }}/s</span></dd>
            <dt class="text-muted">{{ t('ports.rx') }}</dt><dd class="text-end num">{{ (sel.rx_good || 0).toLocaleString(locale) }} <span class="text-ok" v-if="sel.rx_pps">+{{ sel.rx_pps }}/s</span></dd>
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
      <ul v-if="changes.length" class="divide-y divide-line">
        <li v-for="c in changes" :key="c.id" class="px-5 py-2.5 flex items-center gap-3 text-sm">
          <span class="w-7 h-7 rounded-md bg-surface-3 text-muted flex items-center justify-center shrink-0"><Icon :name="changeIcon(c.action)" :size="15" /></span>
          <span class="flex-1 min-w-0 truncate"><span class="text-ink">{{ t('changes.' + c.action) }}</span><span class="text-muted"> · {{ c.username || '?' }}</span></span>
          <span class="text-xs text-muted shrink-0 num">{{ fmtDate(c.created_at) }}</span>
        </li>
      </ul>
      <EmptyState v-else compact icon="history" :title="t('swdash.noChanges')" />
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

const temp = computed(() => sse.data.value?.temperature || status.value?.temperature || '—')
const ports = computed(() => sse.data.value?.ports || initialStats.value)
const settings = computed(() => sse.data.value?.port_settings || initialSettings.value)
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

onMounted(async () => {
  sse.connect()
  try { status.value = await api(`/api/switches/${props.switchId}/status`) } catch (e) {}
  try { initialStats.value = await api(`/api/switches/${props.switchId}/ports/stats`) } catch (e) {}
  try { initialSettings.value = await api(`/api/switches/${props.switchId}/ports`) } catch (e) {}
  try { changes.value = await api(`/api/switches/${props.switchId}/changes?limit=6`) } catch (e) {}
})
</script>
