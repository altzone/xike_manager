<template>
  <div>
    <h1 class="text-xl font-bold text-gray-900 mb-6">System</h1>
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- System Info -->
      <div class="bg-white rounded-xl border p-6">
        <h2 class="font-semibold text-gray-700 mb-4">System Information</h2>
        <dl class="space-y-3 text-sm">
          <div v-for="(v, k) in info" :key="k" class="flex justify-between">
            <dt class="text-gray-500">{{ k }}</dt>
            <dd class="font-medium text-gray-900">{{ v }}</dd>
          </div>
        </dl>
      </div>
      <!-- Network -->
      <div class="bg-white rounded-xl border p-6">
        <h2 class="font-semibold text-gray-700 mb-4">Network</h2>
        <dl class="space-y-3 text-sm">
          <div v-for="(v, k) in network" :key="k" class="flex justify-between">
            <dt class="text-gray-500">{{ k }}</dt>
            <dd class="font-medium text-gray-900">{{ v }}</dd>
          </div>
        </dl>
      </div>
      <!-- STP -->
      <div class="bg-white rounded-xl border p-6">
        <h2 class="font-semibold text-gray-700 mb-4">STP</h2>
        <p class="text-sm text-gray-500">Enabled: <strong>{{ stp.enabled ? 'Yes' : 'No' }}</strong></p>
        <p class="text-sm text-gray-500">Mode: <strong>{{ stp.mode?.toUpperCase() }}</strong></p>
      </div>
      <!-- EEE -->
      <div class="bg-white rounded-xl border p-6">
        <h2 class="font-semibold text-gray-700 mb-4">Energy Efficient Ethernet</h2>
        <p class="text-sm text-gray-500">Status: <strong>{{ eee.eee }}</strong></p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../composables/useApi.js'

const props = defineProps({ switchId: Number })
const info = ref({})
const network = ref({})
const stp = ref({})
const eee = ref({})

onMounted(async () => {
  const s = await api(`/api/switches/${props.switchId}/status`)
  info.value = { Model: s.modle, Firmware: s.fw_ver, Hardware: s.hw_ver, MAC: s.sys_macaddr, Temperature: `${s.temperature}°C` }
  network.value = { IPv4: s.ipAddress, Netmask: s.netmask, Gateway: s.gateway, DHCP: s.dhcpEnabled === '1' ? 'On' : 'Off', IPv6: s.sys_ipv6 }
  stp.value = await api(`/api/switches/${props.switchId}/stp`)
  eee.value = await api(`/api/switches/${props.switchId}/eee`)
})
</script>
