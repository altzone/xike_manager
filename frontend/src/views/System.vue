<template>
  <div class="space-y-6">
    <h1 class="text-xl font-bold text-gray-900">System & Features</h1>

    <!-- System Info + Network -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card title="System">
        <InfoRow v-for="(v, k) in sysInfo" :key="k" :label="k" :value="v"/>
      </Card>
      <Card title="Network">
        <InfoRow v-for="(v, k) in netInfo" :key="k" :label="k" :value="v"/>
      </Card>
    </div>

    <!-- Time & SNTP -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card title="System Time">
        <div class="space-y-3">
          <InfoRow label="Current Time" :value="timeData.timeVal || '-'"/>
          <InfoRow label="Current Date" :value="timeData.dateVal || '-'"/>
          <InfoRow label="Timezone" :value="timeData.timezoneOffsetVal || '-'"/>
          <div class="pt-2 border-t border-gray-100 space-y-2">
            <div class="grid grid-cols-2 gap-2">
              <input v-model="setTime.time" placeholder="HH:MM:SS" class="input-sm"/>
              <input v-model="setTime.date" placeholder="DD/MM/YYYY" class="input-sm"/>
            </div>
            <select v-model="setTime.timezone" class="input-sm w-full">
              <option value="+00:00">UTC +00:00</option>
              <option value="+01:00">UTC +01:00 (CET)</option>
              <option value="+02:00">UTC +02:00 (CEST)</option>
              <option value="-05:00">UTC -05:00 (EST)</option>
              <option value="+08:00">UTC +08:00</option>
            </select>
            <button @click="applyTime" class="btn-primary w-full">Set Time</button>
          </div>
        </div>
      </Card>
      <Card title="SNTP">
        <div class="space-y-3">
          <Toggle label="SNTP Enabled" v-model="sntp.enabled" @update:modelValue="applySntp"/>
          <div v-if="sntp.enabled" class="space-y-2">
            <div>
              <label class="text-xs text-gray-500">Server</label>
              <input v-model="sntp.server" @blur="applySntp" class="input-sm w-full" placeholder="pool.ntp.org"/>
            </div>
            <div>
              <label class="text-xs text-gray-500">Poll interval (30-99999s)</label>
              <input v-model.number="sntp.poll" type="number" min="30" max="99999" @blur="applySntp" class="input-sm w-full"/>
            </div>
          </div>
        </div>
      </Card>
    </div>

    <!-- Feature toggles -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <Card title="STP">
        <Toggle label="Enabled" v-model="stp.enabled" @update:modelValue="applyStp"/>
        <p class="text-xs text-gray-400 mt-1">Spanning Tree Protocol</p>
        <select v-if="stp.enabled" v-model="stp.mode" @change="applyStp" class="input-sm w-full mt-2">
          <option value="stp">STP (Classic)</option>
          <option value="rstp">RSTP (Rapid)</option>
        </select>
      </Card>

      <Card title="Storm Control">
        <Toggle label="Enabled" v-model="storm.enabled" @update:modelValue="applyStorm"/>
        <p class="text-xs text-gray-400 mt-1">Limits broadcast storms</p>
        <div v-if="storm.enabled" class="mt-2">
          <label class="text-xs text-gray-500">Rate (1-1000 pps)</label>
          <input v-model.number="storm.rate" type="number" min="1" max="1000" @blur="applyStorm" class="input-sm w-full"/>
        </div>
      </Card>

      <Card title="IGMP Snooping">
        <Toggle label="Enabled" v-model="igmp.enabled" @update:modelValue="applyIgmp"/>
        <p class="text-xs text-gray-400 mt-1">Multicast optimization</p>
        <div v-if="igmp.enabled" class="mt-2 space-y-1">
          <label class="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input type="checkbox" v-model="igmp.fast_leave" @change="applyIgmp" class="rounded border-gray-300 text-indigo-600"> Fast Leave
          </label>
          <label class="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input type="checkbox" v-model="igmp.querier" @change="applyIgmp" class="rounded border-gray-300 text-indigo-600"> Querier
          </label>
        </div>
      </Card>

      <Card title="Energy Efficient Ethernet">
        <Toggle label="Enabled" v-model="eee.enabled" @update:modelValue="applyEee"/>
        <p class="text-xs text-gray-400 mt-1">Reduces power during low traffic</p>
      </Card>

      <Card title="Port Mirror" class="md:col-span-2">
        <div class="space-y-3">
          <div class="flex items-center gap-3">
            <label class="text-sm text-gray-600">Monitoring port:</label>
            <select v-model.number="mirror.monitoring_port" class="input-sm">
              <option :value="0">Disabled</option>
              <option v-for="p in 10" :key="p" :value="p">Port {{ p }}</option>
            </select>
          </div>
          <div v-if="mirror.monitoring_port > 0" class="space-y-2">
            <div class="flex items-center gap-2">
              <label class="text-sm text-gray-600 w-20">Ingress:</label>
              <select v-model="mirror.ingress" class="input-sm"><option value="1">Enabled</option><option value="0">Disabled</option></select>
            </div>
            <div class="flex items-center gap-2">
              <label class="text-sm text-gray-600 w-20">Egress:</label>
              <select v-model="mirror.egress" class="input-sm"><option value="1">Enabled</option><option value="0">Disabled</option></select>
            </div>
            <div>
              <label class="text-xs text-gray-500 mb-1 block">Mirrored ports:</label>
              <div class="flex flex-wrap gap-1.5">
                <label v-for="p in 10" :key="p" v-show="p !== mirror.monitoring_port"
                  class="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium cursor-pointer transition-all select-none"
                  :class="mirror.mirrored_ports.includes(p) ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-200' : 'bg-gray-100 text-gray-400 hover:bg-gray-200'">
                  <input type="checkbox" :value="p" v-model="mirror.mirrored_ports" class="hidden"> P{{ p }}
                </label>
              </div>
            </div>
            <button @click="applyMirror" class="btn-primary">Apply Mirror</button>
          </div>
        </div>
      </Card>
    </div>

    <!-- Loop Detection -->
    <Card title="Loop Detection">
      <p class="text-xs text-gray-400 mb-3">Enable per port to detect and block loops</p>
      <div class="flex flex-wrap gap-2">
        <button v-for="lp in loop" :key="lp.port" @click="toggleLoop(lp.port)"
          class="px-3 py-2 rounded-lg text-xs font-medium border transition-all"
          :class="lp.enabled ? (lp.violation ? 'bg-red-50 border-red-300 text-red-700 shadow-sm' : 'bg-emerald-50 border-emerald-300 text-emerald-700') : 'bg-gray-50 border-gray-200 text-gray-400 hover:bg-gray-100'">
          Port {{ lp.port }}
          <span v-if="lp.violation" class="ml-1 animate-pulse">LOOP!</span>
        </button>
      </div>
    </Card>

    <!-- Static MAC -->
    <Card title="Static MAC Entries">
      <div class="flex items-center gap-3 mb-3">
        <input v-model="staticMac.mac" placeholder="xx:xx:xx:xx:xx:xx" class="input-sm flex-1"/>
        <input v-model.number="staticMac.port" type="number" min="1" max="10" placeholder="Port" class="input-sm w-20"/>
        <input v-model.number="staticMac.fid" type="number" min="0" max="63" placeholder="FID" class="input-sm w-20"/>
        <button @click="addStaticMac" class="btn-primary">Add</button>
      </div>
      <div v-if="staticMacs.length" class="text-sm space-y-1">
        <div v-for="(m, i) in staticMacs" :key="i" class="flex items-center justify-between py-1 border-b border-gray-50">
          <span class="font-mono">{{ m.mac }}</span>
          <span class="text-gray-500">Port {{ m.port }} / FID {{ m.fid }}</span>
        </div>
      </div>
      <p v-else class="text-xs text-gray-400">No static MAC entries</p>
    </Card>

    <!-- Danger Zone -->
    <div class="bg-white rounded-xl border border-red-200 shadow-sm p-5">
      <h3 class="font-semibold text-red-600 mb-2">Danger Zone</h3>
      <button @click="doReboot" class="px-4 py-2 bg-red-50 text-red-600 text-sm rounded-lg hover:bg-red-100 border border-red-200 transition">
        Reboot Switch
      </button>
    </div>

    <p v-if="msg" class="text-sm transition-all" :class="msgOk ? 'text-emerald-600' : 'text-red-500'">{{ msg }}</p>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, h } from 'vue'
import { api } from '../composables/useApi.js'

const props = defineProps({ switchId: Number })
const sysInfo = ref({})
const netInfo = ref({})
const timeData = ref({})
const setTime = reactive({ time: '', date: '', timezone: '+01:00' })
const sntp = reactive({ enabled: false, server: 'pool.ntp.org', poll: 64 })
const stp = reactive({ enabled: false, mode: 'stp' })
const storm = reactive({ enabled: false, rate: 100 })
const igmp = reactive({ enabled: false, fast_leave: true, querier: false })
const eee = reactive({ enabled: false })
const loop = ref([])
const mirror = reactive({ monitoring_port: 0, ingress: '0', egress: '0', mirrored_ports: [] })
const staticMacs = ref([])
const staticMac = reactive({ mac: '', port: 1, fid: 0 })
const msg = ref('')
const msgOk = ref(true)

function flash(m, ok = true) { msg.value = m; msgOk.value = ok; setTimeout(() => msg.value = '', 3000) }

async function load() {
  const s = await api(`/api/switches/${props.switchId}/status`)
  sysInfo.value = { Model: s.modle, Firmware: s.fw_ver, Hardware: s.hw_ver, MAC: s.sys_macaddr, Temperature: `${s.temperature}C` }
  netInfo.value = { IPv4: s.ipAddress, Netmask: s.netmask, Gateway: s.gateway, DHCP: s.dhcpEnabled === '1' ? 'On' : 'Off' }

  const t = await api(`/api/switches/${props.switchId}/time`)
  timeData.value = t
  sntp.enabled = t.sntp_state === '1'
  sntp.server = t.sntp_server_ip || 'pool.ntp.org'
  sntp.poll = parseInt(t.sntp_poll) || 64

  const st = await api(`/api/switches/${props.switchId}/stp`)
  stp.enabled = st.enabled; stp.mode = st.mode

  const sc = await api(`/api/switches/${props.switchId}/storm`)
  storm.enabled = sc.sctrl_state === '1'; storm.rate = parseInt(sc.sctrl_rate)

  const ig = await api(`/api/switches/${props.switchId}/igmp`)
  igmp.enabled = ig.config.igmp === 'on'; igmp.fast_leave = ig.config.fast_leave === 'on'; igmp.querier = ig.config.snoop_querier === 'on'

  const ee = await api(`/api/switches/${props.switchId}/eee`)
  eee.enabled = ee.eee === 'on'

  loop.value = await api(`/api/switches/${props.switchId}/loop`)

  const mi = await api(`/api/switches/${props.switchId}/mirror`)
  mirror.monitoring_port = mi.monitoring_port
  mirror.mirrored_ports = mi.ports.filter(p => p.ingress || p.egress).map(p => p.port)

  try { const sm = await api(`/api/switches/${props.switchId}/mac/static`); staticMacs.value = sm } catch(e) {}
}

async function applyTime() {
  try {
    await api(`/api/switches/${props.switchId}/time`, { method: 'POST', body: JSON.stringify(setTime) })
    flash('Time set'); await load()
  } catch(e) { flash(e.message, false) }
}
async function applySntp() {
  await api(`/api/switches/${props.switchId}/sntp`, { method: 'POST', body: JSON.stringify(sntp) }); flash('SNTP updated')
}
async function applyStp() {
  await api(`/api/switches/${props.switchId}/stp`, { method: 'POST', body: JSON.stringify({ enabled: stp.enabled, mode: stp.mode }) }); flash('STP updated')
}
async function applyStorm() {
  await api(`/api/switches/${props.switchId}/storm`, { method: 'POST', body: JSON.stringify({ enabled: storm.enabled, rate: storm.rate }) }); flash('Storm control updated')
}
async function applyIgmp() {
  await api(`/api/switches/${props.switchId}/igmp`, { method: 'POST', body: JSON.stringify({ enabled: igmp.enabled, fast_leave: igmp.fast_leave, querier: igmp.querier }) }); flash('IGMP updated')
}
async function applyEee() {
  await api(`/api/switches/${props.switchId}/eee`, { method: 'POST', body: JSON.stringify({ enabled: eee.enabled }) }); flash('EEE updated')
}
async function toggleLoop(port) {
  const lp = loop.value.find(l => l.port === port); lp.enabled = !lp.enabled
  const ports = {}; loop.value.forEach(l => ports[l.port] = l.enabled)
  await api(`/api/switches/${props.switchId}/loop`, { method: 'POST', body: JSON.stringify({ ports }) }); flash(`Loop P${port}: ${lp.enabled ? 'ON' : 'OFF'}`)
}
async function applyMirror() {
  await api(`/api/switches/${props.switchId}/mirror`, { method: 'POST', body: JSON.stringify(mirror) }); flash('Mirror updated')
}
async function addStaticMac() {
  await api(`/api/switches/${props.switchId}/mac/static/add`, { method: 'POST', body: JSON.stringify(staticMac) })
  flash('Static MAC added'); staticMac.mac = ''; await load()
}
async function doReboot() {
  if (!confirm('Reboot the switch?')) return
  await api(`/api/switches/${props.switchId}/reboot`, { method: 'POST' }); flash('Rebooting...')
}

onMounted(load)
</script>

<script>
// Reusable mini-components
const Card = { props: ['title'], template: `<div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5"><h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">{{ title }}</h3><slot/></div>` }
const InfoRow = { props: ['label','value'], template: `<div class="flex justify-between items-center text-sm"><span class="text-gray-500">{{ label }}</span><span class="font-medium text-gray-900">{{ value }}</span></div>` }
const Toggle = { props: ['label','modelValue'], emits: ['update:modelValue'], template: `<div class="flex items-center justify-between"><span class="text-sm text-gray-700">{{ label }}</span><button @click="$emit('update:modelValue', !modelValue)" class="relative w-11 h-6 rounded-full transition-colors duration-200" :class="modelValue ? 'bg-emerald-500' : 'bg-gray-300'"><span class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200" :class="modelValue ? 'translate-x-5' : ''"></span></button></div>` }
export default { components: { Card, InfoRow, Toggle } }
</script>

<style scoped>
.input-sm { padding: 0.375rem 0.75rem; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 0.5rem; font-size: 0.875rem; outline: none; transition: all 0.15s; }
.input-sm:focus { box-shadow: 0 0 0 2px rgba(99,102,241,0.3); border-color: #6366f1; }
.btn-primary { padding: 0.5rem 1rem; background: #4f46e5; color: white; font-size: 0.875rem; border-radius: 0.5rem; cursor: pointer; transition: all 0.15s; border: none; }
.btn-primary:hover { background: #4338ca; }
</style>
