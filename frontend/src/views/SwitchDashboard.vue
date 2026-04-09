<template>
  <div>
    <h1 class="text-xl font-bold text-gray-900 mb-6">{{ t('nav.dashboard') }}</h1>

    <!-- Status cards -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <div class="bg-white rounded-xl border p-4">
        <p class="text-xs text-gray-400 uppercase">{{ t('swdash.temperature') }}</p>
        <p class="text-2xl font-bold mt-1" :class="temp > 60 ? 'text-red-500' : 'text-gray-900'">{{ temp }}°C</p>
      </div>
      <div class="bg-white rounded-xl border p-4">
        <p class="text-xs text-gray-400 uppercase">{{ t('swdash.portsUp') }}</p>
        <p class="text-2xl font-bold mt-1 text-emerald-600">{{ portsUp }} / 10</p>
      </div>
      <div class="bg-white rounded-xl border p-4">
        <p class="text-xs text-gray-400 uppercase">{{ t('swdash.sse') }}</p>
        <p class="text-2xl font-bold mt-1" :class="sse.connected.value ? 'text-emerald-600' : 'text-gray-400'">
          {{ sse.connected.value ? t('sw.online') : t('sw.offline') }}
        </p>
      </div>
      <div class="bg-white rounded-xl border p-4">
        <p class="text-xs text-gray-400 uppercase">{{ t('swdash.model') }}</p>
        <p class="text-lg font-bold mt-1 text-gray-900">{{ model }}</p>
      </div>
    </div>

    <!-- Switch diagram -->
    <div class="bg-white rounded-xl border p-6">
      <h2 class="text-sm font-semibold text-gray-400 uppercase mb-4">{{ t('ports.status') }}</h2>
      <div class="flex gap-2 flex-wrap">
        <div v-for="port in ports" :key="port.port"
          class="w-20 rounded-lg border-2 p-3 text-center transition cursor-pointer hover:shadow-md"
          :class="port.link !== 'Link Down' ? 'border-emerald-400 bg-emerald-50' : 'border-gray-200 bg-gray-50'">
          <div class="text-xs font-bold" :class="port.link !== 'Link Down' ? 'text-emerald-700' : 'text-gray-400'">
            {{ port.port >= 9 ? 'SFP+' : 'P' }}{{ port.port }}
          </div>
          <div class="text-[10px] mt-1" :class="port.link !== 'Link Down' ? 'text-emerald-600' : 'text-gray-300'">
            {{ port.link === 'Link Down' ? t('ports.down') : port.link.replace('MbpsFull','M').replace('MbpsHalf','M/H') }}
          </div>
          <div v-if="port.rx_pps" class="text-[9px] text-gray-400 mt-1">
            {{ port.rx_pps }}rx {{ port.tx_pps }}tx
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useSSE } from '../composables/useSSE.js'
import { api } from '../composables/useApi.js'
import { useI18n } from '../i18n/index.js'

const { t } = useI18n()

const props = defineProps({ switchId: Number })
const sse = useSSE(props.switchId)
const status = ref({})
const model = ref('')

const initialStats = ref([])

const temp = computed(() => sse.data.value?.temperature || status.value?.temperature || '?')
const ports = computed(() => sse.data.value?.ports || initialStats.value)
const portsUp = computed(() => ports.value.filter(p => p.link && p.link !== 'Link Down').length)

onMounted(async () => {
  status.value = await api(`/api/switches/${props.switchId}/status`)
  model.value = status.value?.modle || status.value?.des || ''
  // Load initial stats without SSE
  try { initialStats.value = await api(`/api/switches/${props.switchId}/ports/stats`) } catch(e) {}
  sse.connect()
})
</script>
