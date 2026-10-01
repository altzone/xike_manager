<template>
  <!-- Front panel of the SKS3200-8E2X: 8x RJ45 2.5G + 2x SFP+ 10G.
       The panel is dark in both themes, so its small labels use fixed on-dark colours (slate-400 / violet-300), not theme tokens. -->
  <div dir="ltr" class="rounded-xl bg-[#1b2430] dark:bg-[#0d131b] border border-[#2c3847] p-3 sm:p-4 select-none">
    <div class="flex items-center justify-between mb-3 px-1">
      <div class="flex items-center gap-2 text-[11px] font-medium tracking-wider text-slate-400 uppercase">
        <span class="dot" :class="live ? 'bg-ok live-dot' : 'bg-slate-600'"></span>
        <span>{{ model || 'SKS3200-8E2X' }}</span>
        <span v-if="firmware" class="text-slate-400 normal-case tracking-normal mono">{{ firmware }}</span>
      </div>
      <div class="flex items-center gap-3 text-[10px] text-slate-400">
        <span class="flex items-center gap-1"><span class="dot bg-ok"></span>{{ t('ui.linkUp') }}</span>
        <span class="flex items-center gap-1"><span class="dot bg-warn"></span>{{ t('ports.errors') }}</span>
        <span class="flex items-center gap-1"><span class="dot bg-slate-600"></span>{{ t('ports.down') }}</span>
      </div>
    </div>

    <div class="flex items-stretch gap-2 sm:gap-3">
      <!-- RJ45 block -->
      <div class="flex-1 rounded-lg bg-black/25 p-2 sm:p-2.5">
        <p class="text-[10px] text-slate-400 font-medium tracking-wider uppercase mb-1.5 px-0.5">RJ45 · 2.5G</p>
        <div class="grid grid-cols-4 sm:grid-cols-8 gap-1.5 sm:gap-2">
          <button v-for="p in rj45" :key="p.port" type="button" class="group flex flex-col items-center gap-1 focus-visible:outline-accent rounded"
            :title="tooltip(p)" :aria-label="`${t('ports.port')} ${p.port}`" :aria-pressed="selected === p.port" @click="$emit('select', p.port)">
            <span class="relative w-full aspect-[5/4] max-w-[52px] rounded-[5px] border transition-all"
              :class="[jack(p), selected === p.port ? 'ring-2 ring-accent ring-offset-2 ring-offset-[#1b2430] dark:ring-offset-[#0d131b]' : '']">
              <span class="absolute inset-x-[22%] top-0 h-[22%] rounded-b-[3px] bg-black/40"></span>
              <span class="absolute bottom-1 start-1 w-1.5 h-1.5 rounded-full" :class="led(p)"></span>
              <span v-if="isDisabled(p)" class="absolute bottom-1 end-1 w-1.5 h-1.5 rounded-full bg-danger"></span>
            </span>
            <span class="text-[11px] font-semibold leading-none" :class="selected === p.port ? 'text-white' : 'text-slate-300'">{{ p.port }}</span>
            <span class="text-[9px] leading-none mono" :class="isUp(p) ? 'text-[#22c55e]' : 'text-slate-500'">{{ isUp(p) ? shortSpeed(p.link, p.port) : "—" }}</span>
          </button>
        </div>
      </div>
      <!-- SFP+ block -->
      <div class="rounded-lg bg-black/25 p-2 sm:p-2.5 w-[132px] sm:w-[164px] shrink-0">
        <p class="text-[10px] text-[#a78bfa] font-medium tracking-wider uppercase mb-1.5 px-0.5">SFP+ · 10G</p>
        <div class="grid grid-cols-2 gap-1.5 sm:gap-2">
          <button v-for="p in sfp" :key="p.port" type="button" class="group flex flex-col items-center gap-1 focus-visible:outline-accent rounded"
            :title="tooltip(p)" :aria-label="`${t('ports.port')} ${p.port} SFP+`" :aria-pressed="selected === p.port" @click="$emit('select', p.port)">
            <span class="relative w-full aspect-[5/4] max-w-[64px] rounded-[4px] border transition-all"
              :class="[jack(p, true), selected === p.port ? 'ring-2 ring-accent ring-offset-2 ring-offset-[#1b2430] dark:ring-offset-[#0d131b]' : '']">
              <span class="absolute inset-x-[12%] top-[28%] h-[44%] rounded-[2px] bg-black/50 border border-black/60"></span>
              <span class="absolute bottom-1 start-1 w-1.5 h-1.5 rounded-full" :class="led(p)"></span>
              <span v-if="isDisabled(p)" class="absolute bottom-1 end-1 w-1.5 h-1.5 rounded-full bg-danger"></span>
            </span>
            <span class="text-[11px] font-semibold leading-none" :class="selected === p.port ? 'text-white' : 'text-slate-300'">{{ p.port }}</span>
            <span class="text-[9px] leading-none mono" :class="isUp(p) ? 'text-[#a78bfa]' : 'text-slate-500'">{{ isUp(p) ? shortSpeed(p.link, p.port) : "—" }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../i18n/index.js'

const props = defineProps({
  ports: { type: Array, default: () => [] },      // from /ports/stats or SSE: {port, link, tx_good, rx_good, tx_bad, rx_bad, tx_pps, rx_pps}
  settings: { type: Array, default: () => [] },   // from /ports: {port, status, description}
  selected: Number,
  live: Boolean,
  model: String,
  firmware: String,
})
defineEmits(['select'])
const { t } = useI18n()

const byPort = computed(() => Object.fromEntries(props.settings.map(s => [s.port, s])))
const filled = computed(() => {
  const map = Object.fromEntries(props.ports.map(p => [p.port, p]))
  return Array.from({ length: 10 }, (_, i) => map[i + 1] || { port: i + 1, link: '' })
})
const rj45 = computed(() => filled.value.filter(p => p.port <= 8))
const sfp = computed(() => filled.value.filter(p => p.port >= 9))

function isUp(p) { return !!p.link && p.link !== 'Link Down' }
function isDisabled(p) { return byPort.value[p.port]?.status === 'Disabled' }
function hasErrors(p) { return (p.tx_bad || 0) + (p.rx_bad || 0) > 0 }
// the firmware puts the negotiated speed either in the stats' Link_Status or in the port's Spd_Duplex_Actual
const SHORT_SPEED = { '10GbpsFull': '10G', '2500MbpsFull': '2.5G', '1000MbpsFull': '1G', '100MbpsFull': '100M', '100MbpsHalf': '100M½', '10MbpsFull': '10M', '10MbpsHalf': '10M½' }
function shortSpeed(link, port) {
  const raw = [link, byPort.value[port]?.speed_actual].find(v => v && !/^link/i.test(v)) || ''
  // same spelling as the Ports table (2.5G, 10G, 1G, 100M…)
  return SHORT_SPEED[raw] || raw.replace('MbpsFull', 'M').replace('MbpsHalf', 'M½').replace('GbpsFull', 'G') || '↑'
}
function led(p) {
  if (hasErrors(p)) return 'bg-warn shadow-[0_0_6px_var(--sp-warn)]'
  if (isUp(p)) return 'bg-ok shadow-[0_0_6px_var(--sp-ok)]'
  return 'bg-slate-600'
}
function jack(p, isSfp = false) {
  if (isUp(p)) return isSfp ? 'bg-[#2d2a4a] border-sfp/60' : 'bg-[#243041] border-ok/50'
  return 'bg-[#222b38] border-[#3a4658] group-hover:border-slate-400'
}
function tooltip(p) {
  const s = byPort.value[p.port]
  const parts = [`${t('ports.port')} ${p.port}${s?.description ? ' · ' + s.description : ''}`, isUp(p) ? p.link : t('ports.down')]
  if (isUp(p)) parts.push(`TX ${(p.tx_good || 0).toLocaleString()} · RX ${(p.rx_good || 0).toLocaleString()}`)
  if (hasErrors(p)) parts.push(`${t('ports.errors')}: ${(p.tx_bad || 0) + (p.rx_bad || 0)}`)
  return parts.join('\n')
}
</script>
