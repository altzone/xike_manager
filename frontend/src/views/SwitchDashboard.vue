<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-bold text-gray-900">{{ t('nav.dashboard') }}</h1>
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full" :class="sse.connected.value ? 'bg-emerald-500 animate-pulse' : 'bg-gray-300'"></span>
        <span class="text-xs" :class="sse.connected.value ? 'text-emerald-600' : 'text-gray-400'">{{ sse.connected.value ? 'Live' : 'Connecting...' }}</span>
      </div>
    </div>

    <!-- Stats Cards -->
    <div class="grid grid-cols-2 lg:grid-cols-5 gap-4">
      <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex items-center gap-3">
        <div class="w-10 h-10 rounded-lg flex items-center justify-center" :class="Number(temp) > 55 ? 'bg-red-100' : 'bg-emerald-100'">
          <svg class="w-5 h-5" :class="Number(temp) > 55 ? 'text-red-600' : 'text-emerald-600'" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z"/>
          </svg>
        </div>
        <div>
          <p class="text-[10px] text-gray-400 uppercase font-semibold tracking-wider">{{ t('swdash.temperature') }}</p>
          <p class="text-lg font-bold" :class="Number(temp) > 55 ? 'text-red-600' : 'text-gray-900'">{{ temp }}°C</p>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex items-center gap-3">
        <div class="w-10 h-10 rounded-lg bg-indigo-100 flex items-center justify-center">
          <svg class="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
          </svg>
        </div>
        <div>
          <p class="text-[10px] text-gray-400 uppercase font-semibold tracking-wider">{{ t('swdash.portsUp') }}</p>
          <p class="text-lg font-bold text-gray-900">{{ portsUp }} <span class="text-sm font-normal text-gray-400">/ 10</span></p>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex items-center gap-3">
        <div class="w-10 h-10 rounded-lg bg-sky-100 flex items-center justify-center">
          <svg class="w-5 h-5 text-sky-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"/>
          </svg>
        </div>
        <div>
          <p class="text-[10px] text-gray-400 uppercase font-semibold tracking-wider">Total TX</p>
          <p class="text-lg font-bold text-gray-900">{{ formatPkts(totalTx) }}</p>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex items-center gap-3">
        <div class="w-10 h-10 rounded-lg bg-violet-100 flex items-center justify-center">
          <svg class="w-5 h-5 text-violet-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3"/>
          </svg>
        </div>
        <div>
          <p class="text-[10px] text-gray-400 uppercase font-semibold tracking-wider">Total RX</p>
          <p class="text-lg font-bold text-gray-900">{{ formatPkts(totalRx) }}</p>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex items-center gap-3">
        <div class="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center">
          <svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2"/>
          </svg>
        </div>
        <div>
          <p class="text-[10px] text-gray-400 uppercase font-semibold tracking-wider">{{ t('swdash.model') }}</p>
          <p class="text-sm font-bold text-gray-900 truncate">{{ model }}</p>
        </div>
      </div>
    </div>

    <!-- Switch Visual -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="bg-gradient-to-r from-slate-800 to-slate-700 px-6 py-4 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-3 h-3 rounded-full" :class="sse.connected.value ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'"></div>
          <span class="text-white font-semibold text-sm">{{ model || 'SKS3200-8E2X' }}</span>
          <span class="text-slate-400 text-xs">{{ firmware }}</span>
        </div>
        <span class="text-slate-400 text-xs">{{ temp }}°C</span>
      </div>

      <!-- Port strip -->
      <div class="px-6 py-5 bg-slate-50">
        <div class="flex gap-2 mb-2">
          <p class="text-[10px] text-gray-400 uppercase font-semibold tracking-wider flex-1">RJ45 2.5G</p>
          <p class="text-[10px] text-gray-400 uppercase font-semibold tracking-wider" style="width: 176px;">SFP+ 10G</p>
        </div>
        <div class="flex gap-2">
          <!-- RJ45 ports 1-8 -->
          <div v-for="p in portsByType.rj45" :key="p.port"
            class="flex-1 rounded-lg border-2 p-2.5 text-center transition-all duration-300 cursor-default relative group"
            :class="isUp(p) ? 'border-emerald-400 bg-white shadow-sm shadow-emerald-100' : 'border-gray-200 bg-white'">
            <div class="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full border-2 border-white"
              :class="isUp(p) ? 'bg-emerald-500' : 'bg-gray-300'"></div>
            <div class="text-xs font-bold" :class="isUp(p) ? 'text-gray-900' : 'text-gray-400'">{{ p.port }}</div>
            <div class="text-[9px] mt-0.5 font-medium" :class="isUp(p) ? 'text-emerald-600' : 'text-gray-300'">
              {{ isUp(p) ? shortSpeed(p.link) : '—' }}
            </div>
            <div v-if="p.rx_pps > 0 || p.tx_pps > 0" class="text-[8px] text-indigo-500 mt-0.5 font-mono">
              {{ p.rx_pps + p.tx_pps }}/s
            </div>
            <!-- Hover detail -->
            <div class="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 bg-gray-900 text-white text-[10px] rounded-lg px-3 py-2 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10 w-36 pointer-events-none">
              <div class="font-bold mb-1">Port {{ p.port }}</div>
              <div>{{ isUp(p) ? p.link : t('ports.down') }}</div>
              <div v-if="isUp(p)">TX: {{ p.tx_good?.toLocaleString() }}</div>
              <div v-if="isUp(p)">RX: {{ p.rx_good?.toLocaleString() }}</div>
              <div v-if="p.tx_bad + p.rx_bad > 0" class="text-red-300">Errors: {{ p.tx_bad + p.rx_bad }}</div>
              <span class="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"></span>
            </div>
          </div>
          <!-- Separator -->
          <div class="w-px bg-gray-200 mx-1"></div>
          <!-- SFP+ ports 9-10 -->
          <div v-for="p in portsByType.sfp" :key="p.port"
            class="w-20 rounded-lg border-2 p-2.5 text-center transition-all duration-300 cursor-default relative group"
            :class="isUp(p) ? 'border-violet-400 bg-white shadow-sm shadow-violet-100' : 'border-gray-200 bg-white'">
            <div class="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full border-2 border-white"
              :class="isUp(p) ? 'bg-violet-500' : 'bg-gray-300'"></div>
            <div class="text-[9px] text-violet-500 font-semibold">SFP+</div>
            <div class="text-xs font-bold" :class="isUp(p) ? 'text-gray-900' : 'text-gray-400'">{{ p.port }}</div>
            <div class="text-[9px] mt-0.5 font-medium" :class="isUp(p) ? 'text-violet-600' : 'text-gray-300'">
              {{ isUp(p) ? shortSpeed(p.link) : '—' }}
            </div>
            <div v-if="p.rx_pps > 0 || p.tx_pps > 0" class="text-[8px] text-indigo-500 mt-0.5 font-mono">
              {{ p.rx_pps + p.tx_pps }}/s
            </div>
            <!-- Hover detail -->
            <div class="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 bg-gray-900 text-white text-[10px] rounded-lg px-3 py-2 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10 w-36 pointer-events-none">
              <div class="font-bold mb-1">Port {{ p.port }} (SFP+)</div>
              <div>{{ isUp(p) ? p.link : t('ports.down') }}</div>
              <div v-if="isUp(p)">TX: {{ p.tx_good?.toLocaleString() }}</div>
              <div v-if="isUp(p)">RX: {{ p.rx_good?.toLocaleString() }}</div>
              <span class="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900"></span>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useSSE } from '../composables/useSSE.js'
import { api } from '../composables/useApi.js'
import { useI18n } from '../i18n/index.js'

const { t } = useI18n()
const props = defineProps({ switchId: Number })
const sse = useSSE(props.switchId)
const status = ref({})
const model = ref('')
const firmware = ref('')
const initialStats = ref([])

const temp = computed(() => sse.data.value?.temperature || status.value?.temperature || '?')
const ports = computed(() => sse.data.value?.ports || initialStats.value)
const portsUp = computed(() => ports.value.filter(p => isUp(p)).length)
const totalTx = computed(() => ports.value.reduce((s, p) => s + (p.tx_good || 0), 0))
const totalRx = computed(() => ports.value.reduce((s, p) => s + (p.rx_good || 0), 0))

const portsByType = computed(() => ({
  rj45: ports.value.filter(p => p.port < 9),
  sfp: ports.value.filter(p => p.port >= 9),
}))

function isUp(p) { return p.link && p.link !== 'Link Down' }

function shortSpeed(link) {
  if (!link) return ''
  return link.replace('MbpsFull', 'M').replace('MbpsHalf', 'M/H').replace('GbpsFull', 'G')
}

function formatPkts(n) {
  if (!n) return '0'
  if (n >= 1000000000) return (n / 1000000000).toFixed(1) + 'G'
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return n.toString()
}

onMounted(async () => {
  status.value = await api(`/api/switches/${props.switchId}/status`)
  model.value = status.value?.modle || status.value?.des || ''
  firmware.value = status.value?.fw_ver || ''
  try { initialStats.value = await api(`/api/switches/${props.switchId}/ports/stats`) } catch(e) {}
  sse.connect()
})
</script>
