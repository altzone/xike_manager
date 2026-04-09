<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <div class="flex items-center gap-2"><h1 class="text-xl font-bold text-gray-900">{{ t('lag.title') }}</h1><Tip :title="t('lag.title')">{{ t('lag.tip') }}</Tip></div>
        <p class="text-sm text-gray-400 mt-1">{{ t('lag.desc') }}</p>
      </div>
      <button @click="showCreate = true"
        class="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition shadow-sm flex items-center gap-1.5">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
        {{ t('lag.create') }}
      </button>
    </div>

    <!-- Active LAG Groups -->
    <div v-if="groups.length" class="space-y-4">
      <div v-for="g in groups" :key="g.id" class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div class="px-5 py-4 flex items-center justify-between">
          <div class="flex items-center gap-4">
            <div class="w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold"
              :class="g.allUp ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'">
              G{{ g.id }}
            </div>
            <div>
              <div class="flex items-center gap-2">
                <h3 class="font-semibold text-gray-900">
                <input v-model="groupNames[g.id]" @blur="renameGroup(g.id)"
                  class="bg-transparent border-0 border-b border-transparent hover:border-gray-300 focus:border-indigo-500 outline-none font-semibold text-gray-900 px-0 py-0 w-48"
                  :placeholder="`LAG Group ${g.id}`"/>
              </h3>
                <span class="text-[10px] px-2 py-0.5 rounded-full font-medium"
                  :class="g.mode === 2 ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600'">
                  {{ g.mode === 2 ? t('lag.lacp') : t('lag.static') }}
                </span>
              </div>
              <p class="text-xs text-gray-400 mt-0.5">{{ g.ports.length }} ports &mdash; {{ g.ports.length * (g.ports[0]?.speed || 2.5) }}G aggregate</p>
            </div>
          </div>
          <button @click="removeGroup(g.id)" class="text-gray-300 hover:text-red-500 transition p-2" title="Remove LAG group">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
          </button>
        </div>
        <div class="px-5 pb-4">
          <div class="flex gap-2">
            <div v-for="p in g.ports" :key="p.port"
              class="flex-1 rounded-lg border-2 p-3 text-center transition"
              :class="p.state === 1 ? 'border-emerald-300 bg-emerald-50' : 'border-gray-200 bg-gray-50'">
              <div class="text-sm font-bold" :class="p.state === 1 ? 'text-emerald-700' : 'text-gray-400'">
                {{ p.port >= 9 ? 'SFP+' : 'P' }}{{ p.port }}
              </div>
              <div class="text-[10px] mt-1" :class="p.state === 1 ? 'text-emerald-600' : 'text-gray-300'">
                {{ p.state === 1 ? t('lag.active') : t('ports.down') }}
              </div>
              <div v-if="g.mode === 2" class="text-[9px] text-gray-400 mt-1">
                {{ p.timeout === 0 ? 'Fast' : 'Slow' }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else class="bg-white rounded-xl border border-gray-200 shadow-sm p-12 text-center">
      <div class="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
        <svg class="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5"/>
        </svg>
      </div>
      <p class="text-gray-500 font-medium">{{ t('lag.noGroups') }}</p>
      <p class="text-gray-400 text-sm mt-1">{{ t('lag.createDesc') }}</p>
    </div>

    <!-- LACP System Priority -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div class="flex items-center gap-4">
        <div>
          <h3 class="text-sm font-semibold text-gray-700">{{ t('lag.priority') }}</h3>
          <p class="text-xs text-gray-400">{{ t('lag.priorityDesc') }}</p>
        </div>
        <input v-model.number="systemPriority" type="number" min="0" max="65535"
          class="w-28 px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"/>
        <button @click="applyPriority" class="px-3 py-1.5 bg-indigo-600 text-white text-xs rounded-lg hover:bg-indigo-700 transition">{{ t('lag.save') }}</button>
      </div>
    </div>

    <!-- Create Modal -->
    <div v-if="showCreate" class="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50" @click.self="showCreate = false">
      <div class="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl">
        <h2 class="text-lg font-bold text-gray-900 mb-4">{{ t('lag.create') }}</h2>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('lag.name') }}</label>
            <input v-model="newGroup.name" placeholder="e.g. Uplink-Switch, Server-Bond..."
              class="w-full px-3 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"/>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('lag.groupNum') }}</label>
            <select v-model.number="newGroup.id" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none">
              <option v-for="n in availableGroupIds" :key="n" :value="n">Group {{ n }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('lag.mode') }}</label>
            <div class="grid grid-cols-2 gap-2">
              <button @click="newGroup.mode = 1" class="px-4 py-3 rounded-lg border-2 text-sm font-medium transition text-left"
                :class="newGroup.mode === 1 ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-gray-200 text-gray-500 hover:border-gray-300'">
                <div class="font-bold">{{ t('lag.static') }}</div>
                <div class="text-xs opacity-70 mt-0.5">{{ t('lag.staticDesc') }}</div>
              </button>
              <button @click="newGroup.mode = 2" class="px-4 py-3 rounded-lg border-2 text-sm font-medium transition text-left"
                :class="newGroup.mode === 2 ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-gray-200 text-gray-500 hover:border-gray-300'">
                <div class="font-bold">{{ t('lag.lacp') }}</div>
                <div class="text-xs opacity-70 mt-0.5">{{ t('lag.lacpDesc') }}</div>
              </button>
            </div>
          </div>
          <div v-if="newGroup.mode === 2">
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('lag.timeout') }}</label>
            <select v-model.number="newGroup.timeout" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none">
              <option :value="0">{{ t('lag.timeoutShort') }}</option>
              <option :value="1">{{ t('lag.timeoutLong') }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">{{ t('lag.selectPorts') }}</label>
            <div class="grid grid-cols-5 gap-2">
              <button v-for="p in availablePorts" :key="p.port" @click="togglePort(p.port)"
                class="rounded-lg border-2 p-2 text-center transition text-xs font-medium"
                :class="newGroup.ports.includes(p.port) ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-gray-200 text-gray-400 hover:border-gray-300'">
                {{ p.port >= 9 ? 'SFP+' : 'P' }}{{ p.port }}
                <div class="text-[9px] opacity-60">{{ p.port >= 9 ? '10G' : '2.5G' }}</div>
              </button>
            </div>
            <p v-if="newGroup.ports.length < 2" class="text-xs text-amber-600 mt-2">{{ t('lag.minPorts') }}</p>
          </div>
          <div class="flex gap-3 pt-1">
            <button @click="showCreate = false" class="flex-1 py-2.5 border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 transition">{{ t('common.cancel') }}</button>
            <button @click="createGroup" :disabled="newGroup.ports.length < 2 || applying"
              class="flex-1 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition disabled:opacity-50">
              {{ applying ? t('lag.applying') : t('vlans.create') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <p v-if="msg" class="text-sm" :class="msgOk ? 'text-emerald-600' : 'text-red-500'">{{ msg }}</p>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { api } from '../composables/useApi.js'
import { useToast } from '../composables/useToast.js'
import { useI18n } from '../i18n/index.js'
import Tip from '../components/Tip.vue'

const props = defineProps({ switchId: Number })
const toast = useToast()
const { t } = useI18n()
const allPorts = ref([])
const groupNames = ref({})
const systemPriority = ref(32768)
const showCreate = ref(false)
const applying = ref(false)
const msg = ref('')
const msgOk = ref(true)
const newGroup = reactive({ id: 1, name: '', mode: 2, timeout: 0, ports: [] })

function flash(m, ok = true) { ok ? toast.success(m) : toast.error(m) }

const groups = computed(() => {
  const map = {}
  allPorts.value.filter(p => p.group > 0 && p.type > 0).forEach(p => {
    if (!map[p.group]) map[p.group] = { id: p.group, name: groupNames.value[p.group] || '', mode: p.type, ports: [], allUp: true }
    map[p.group].ports.push(p)
    if (p.state !== 1) map[p.group].allUp = false
  })
  return Object.values(map).sort((a, b) => a.id - b.id)
})

const usedPorts = computed(() => new Set(allPorts.value.filter(p => p.group > 0 && p.type > 0).map(p => p.port)))
const usedGroupIds = computed(() => new Set(groups.value.map(g => g.id)))
const availablePorts = computed(() => allPorts.value.filter(p => !usedPorts.value.has(p.port)))
const availableGroupIds = computed(() => {
  const ids = []
  for (let i = 1; i <= 16; i++) { if (!usedGroupIds.value.has(i)) ids.push(i) }
  return ids
})

function togglePort(port) {
  const idx = newGroup.ports.indexOf(port)
  if (idx >= 0) newGroup.ports.splice(idx, 1)
  else newGroup.ports.push(port)
}

async function load() {
  const data = await api(`/api/switches/${props.switchId}/lag`)
  systemPriority.value = data.system_priority
  allPorts.value = data.ports
  groupNames.value = data.group_names || {}
}

async function createGroup() {
  applying.value = true
  try {
    const ports = allPorts.value.map(p => {
      if (newGroup.ports.includes(p.port)) {
        return { ...p, type: newGroup.mode, group: newGroup.id, timeout: newGroup.timeout }
      }
      return p
    })
    const names = { ...groupNames.value, [newGroup.id]: newGroup.name || `Group ${newGroup.id}` }
    await api(`/api/switches/${props.switchId}/lag`, {
      method: 'POST', body: JSON.stringify({ system_priority: systemPriority.value, ports, group_names: names })
    })
    showCreate.value = false
    newGroup.ports = []; newGroup.name = ''; newGroup.id = availableGroupIds.value[0] || 1
    flash(t('lag.created'))
    await load()
  } catch (e) { flash(e.message, false) }
  finally { applying.value = false }
}

async function removeGroup(groupId) {
  if (!confirm(t('lag.removeConfirm', { id: groupId }))) return
  const ports = allPorts.value.map(p => {
    if (p.group === groupId) return { ...p, type: 0, group: 0, timeout: 0 }
    return p
  })
  await api(`/api/switches/${props.switchId}/lag`, {
    method: 'POST', body: JSON.stringify({ system_priority: systemPriority.value, ports })
  })
  flash(t('lag.removed'))
  await load()
}

async function renameGroup(groupId) {
  await api(`/api/switches/${props.switchId}/lag`, {
    method: 'POST', body: JSON.stringify({ system_priority: systemPriority.value, ports: allPorts.value, group_names: groupNames.value })
  })
  flash(t('common.success'))
}

async function applyPriority() {
  await api(`/api/switches/${props.switchId}/lag`, {
    method: 'POST', body: JSON.stringify({ system_priority: systemPriority.value, ports: allPorts.value })
  })
  flash(t('lag.priorityUpdated'))
}

onMounted(async () => {
  await load()
  newGroup.id = availableGroupIds.value[0] || 1
})
</script>
