<template>
  <div class="space-y-5">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <p class="hint max-w-2xl">{{ t('ports.tip') }}</p>
      <span class="flex items-center gap-1.5 text-xs shrink-0" :class="sse.connected.value ? 'text-ok' : 'text-muted'">
        <span class="dot" :class="sse.connected.value ? 'bg-ok live-dot' : 'bg-faint'"></span>{{ sse.connected.value ? t('ui.live') : t('ui.connecting') }}
      </span>
    </div>

    <Faceplate :ports="statsList" :settings="ports" :selected="selected" :live="sse.connected.value" @select="selected = selected === $event ? null : $event" />

    <div class="card overflow-hidden">
      <div class="overflow-x-auto">
        <table class="table">
          <thead>
            <tr>
              <th>{{ t('ports.port') }}</th>
              <th class="w-[22%]"><span class="inline-flex items-center gap-1">{{ t('ports.desc') }} <Tip :text="t('ports.descTip')" /></span></th>
              <th><span class="inline-flex items-center gap-1">{{ t('ports.status') }} <Tip :text="t('ports.statusTip')" /></span></th>
              <th><span class="inline-flex items-center gap-1">{{ t('ports.speed') }} <Tip :title="t('ports.speed')" :text="t('ports.speedTip')" /></span></th>
              <th>{{ t('ports.actual') }}</th>
              <th><span class="inline-flex items-center gap-1">{{ t('ports.flow') }} <Tip :title="t('ports.flow')" :text="t('ports.flowTip')" /></span></th>
              <th class="!text-end"><span class="inline-flex items-center gap-1">{{ t('ports.tx') }} <Tip :text="t('ports.txTip')" /></span></th>
              <th class="!text-end"><span class="inline-flex items-center gap-1">{{ t('ports.rx') }} <Tip :text="t('ports.rxTip')" /></span></th>
              <th class="!text-end"><span class="inline-flex items-center gap-1">{{ t('ports.errors') }} <Tip :text="t('ports.errorsTip')" /></span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="port in ports" :key="port.port" :class="selected === port.port ? 'bg-accent-soft/40' : ''" @click="selected = port.port">
              <td>
                <div class="flex items-center gap-2">
                  <span class="dot" :class="isUp(port.port) ? 'bg-ok live-dot' : 'bg-line-strong'"></span>
                  <span class="font-semibold w-5 text-ink" :title="port.internal_port && port.internal_port !== port.port ? t('ports.internalIdx', { n: port.internal_port }) : ''">{{ port.port }}</span>
                  <Badge :tone="port.type?.includes('SFP') ? 'sfp' : 'rj45'">{{ port.type?.includes('SFP') ? 'SFP+' : 'RJ45' }}</Badge>
                  <Badge v-if="port.port === 1" tone="warn" :title="t('sys.mgmtIface')">{{ t('vlans.mgmt') }}</Badge>
                </div>
              </td>
              <td>
                <input v-model="port.description" @blur="saveDesc(port)" @keydown.enter="$event.target.blur()" :disabled="!auth.isAdmin" maxlength="128"
                  class="w-full bg-transparent border-0 border-b border-transparent hover:border-line-strong focus:border-accent outline-none px-0.5 py-0.5 text-sm text-ink placeholder:text-faint transition disabled:cursor-default"
                  :placeholder="auth.isAdmin ? t('ports.addDesc') : '—'" />
              </td>
              <td>
                <div class="flex items-center gap-2">
                  <Toggle :model-value="port.status === 'Enabled'" size="sm" :disabled="!auth.isAdmin || busy === port.port" :label="t('ports.status')" @update:model-value="togglePort(port)" />
                  <span class="text-xs" :class="port.status === 'Enabled' ? 'text-ok-ink' : 'text-danger-ink'">{{ port.status === 'Enabled' ? t('ports.enabled') : t('ports.disabled') }}</span>
                </div>
              </td>
              <td>
                <select v-model="port.speed_config" @change="applyPort(port)" :disabled="!auth.isAdmin || busy === port.port" class="select select-sm w-[118px]">
                  <option v-for="o in speedOptions(port)" :key="o.v" :value="o.v">{{ o.l }}</option>
                </select>
              </td>
              <td><span class="mono" :class="isUp(port.port) ? 'text-ink' : 'text-faint'">{{ isUp(port.port) ? negotiated(port) : t('ports.down') }}</span></td>
              <td>
                <Toggle :model-value="port.flow_ctrl_config === 'On'" size="sm" :disabled="!auth.isAdmin || busy === port.port" :label="t('ports.flow')" @update:model-value="toggleFlow(port)" />
              </td>
              <td class="text-end num text-ink-2">
                {{ (stats[port.port]?.tx_good || 0).toLocaleString(locale) }}
                <span v-if="stats[port.port]?.tx_pps > 0" class="text-ok ms-1">+{{ stats[port.port].tx_pps }}/s</span>
              </td>
              <td class="text-end num text-ink-2">
                {{ (stats[port.port]?.rx_good || 0).toLocaleString(locale) }}
                <span v-if="stats[port.port]?.rx_pps > 0" class="text-ok ms-1">+{{ stats[port.port].rx_pps }}/s</span>
              </td>
              <td class="text-end">
                <Badge v-if="errors(port.port) > 0" tone="danger">{{ errors(port.port).toLocaleString(locale) }}</Badge>
                <span v-else class="num text-faint">0</span>
              </td>
            </tr>
            <tr v-if="!ports.length && !loadError"><td colspan="9" class="text-center text-muted py-8">{{ t('common.loading') }}</td></tr>
            <tr v-if="loadError"><td colspan="9"><EmptyState compact icon="x-circle" :title="t('common.failedLoad')" :text="loadError"><Btn size="sm" icon="refresh" @click="reload">{{ t('ui.retry') }}</Btn></EmptyState></td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../composables/useApi.js'
import { useSSE } from '../composables/useSSE.js'
import { useToast } from '../composables/useToast.js'
import { useConfirm } from '../composables/useConfirm.js'
import { useAuthStore } from '../stores/auth.js'
import { useI18n } from '../i18n/index.js'
import Tip from '../components/Tip.vue'
import Badge from '../components/ui/Badge.vue'
import Toggle from '../components/ui/Toggle.vue'
import Btn from '../components/ui/Btn.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import Faceplate from '../components/Faceplate.vue'

const props = defineProps({ switchId: Number })
const { t, locale } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()
const sse = useSSE(props.switchId)

const ports = ref([])
const initialStats = ref([])
const selected = ref(null)
const busy = ref(null)
const loadError = ref('')
const descCache = {}

const statsList = computed(() => sse.data.value?.ports || initialStats.value)
const stats = computed(() => Object.fromEntries(statsList.value.map(s => [s.port, s])))
function isUp(port) { const l = stats.value[port]?.link; return !!l && l !== 'Link Down' }
function errors(port) { return (stats.value[port]?.tx_bad || 0) + (stats.value[port]?.rx_bad || 0) }
// negotiated speed: Spd_Duplex_Actual from the port settings, else whatever the stats' link field says
function negotiated(port) { const s = port.speed_actual; return s && !/^link/i.test(s) ? s : (stats.value[port.port]?.link || '') }

const RJ45_SPEEDS = [['Auto', 'Auto'], ['10Mbps Half', '10M Half'], ['10Mbps Full', '10M Full'], ['100Mbps Half', '100M Half'], ['100Mbps Full', '100M Full'], ['1000Mbps Full', '1G Full'], ['2500Mbps Full', '2.5G Full']]
const SFP_SPEEDS = [['Auto', 'Auto'], ['1000Mbps Full', '1G Full'], ['2500Mbps Full', '2.5G Full'], ['10Gbps Full', '10G Full']]
function speedOptions(port) {
  const list = (port.type?.includes('SFP') ? SFP_SPEEDS : RJ45_SPEEDS).map(([v, l]) => ({ v, l }))
  if (port.speed_config && !list.some(o => o.v === port.speed_config)) list.push({ v: port.speed_config, l: port.speed_config })
  return list
}

async function saveDesc(port) {
  if (descCache[port.port] === port.description) return
  try {
    await api(`/api/switches/${props.switchId}/ports/description`, { method: 'POST', body: JSON.stringify({ port: port.port, description: port.description || '' }) })
    descCache[port.port] = port.description
    toast.success(t('ports.descSaved', { port: port.port }))
  } catch (e) { toast.error(e.message) }
}

async function applyPort(port, overrides = {}) {
  const next = { enabled: port.status === 'Enabled', speed: port.speed_config, flow_ctrl: port.flow_ctrl_config, ...overrides }
  // the backend wants force whenever port 1 is sent disabled; only ask when this change disables it
  const mgmtDisabled = port.port === 1 && !next.enabled
  const disablingMgmt = mgmtDisabled && port.status === 'Enabled'
  if (disablingMgmt && !await confirm({ title: t('ports.port') + ' 1', message: t('ports.confirmMgmt'), danger: true, confirmText: t('ports.disabled') })) {
    await reload(); return
  }
  busy.value = port.port
  try {
    const res = await api(`/api/switches/${props.switchId}/ports/config`, {
      method: 'POST', body: JSON.stringify([{ port: port.port, ...next, force: mgmtDisabled }])
    })
    toast.success(t('ports.updated', { port: port.port }))
    for (const w of res.warnings || []) toast.error(w)
  } catch (e) { toast.error(e.message) }
  finally { busy.value = null; await reload() }
}
function togglePort(port) { applyPort(port, { enabled: port.status !== 'Enabled' }) }
function toggleFlow(port) { applyPort(port, { flow_ctrl: port.flow_ctrl_config === 'On' ? 'Off' : 'On' }) }

async function reload() {
  try {
    ports.value = await api(`/api/switches/${props.switchId}/ports`)
    for (const p of ports.value) descCache[p.port] = p.description
    loadError.value = ''
  } catch (e) { loadError.value = e.message }
}

onMounted(async () => {
  sse.connect()
  await reload()
  try { initialStats.value = await api(`/api/switches/${props.switchId}/ports/stats`) } catch (e) {}
})
</script>
