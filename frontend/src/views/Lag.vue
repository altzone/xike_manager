<template>
  <div class="space-y-5">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <p class="hint max-w-2xl">{{ t('lag.tip') }}</p>
      <Btn v-if="can('lag')" variant="primary" icon="plus" @click="openCreate">{{ t('lag.create') }}</Btn>
    </div>

    <div v-if="groups.length" class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div v-for="g in groups" :key="g.id" class="card">
        <div class="card-head items-center">
          <div class="flex items-center gap-3 min-w-0">
            <span class="w-11 h-11 rounded-lg flex items-center justify-center font-semibold shrink-0" :class="g.allUp ? 'bg-ok-soft text-ok-ink' : 'bg-warn-soft text-warn-ink'">G{{ g.id }}</span>
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <input v-if="auth.isAdmin" v-model="names[g.id]" @blur="rename(g.id)" @keydown.enter="$event.target.blur()" maxlength="64" :aria-label="`${t('lag.name')} – LAG ${g.id}`"
                  class="bg-transparent border-0 border-b border-transparent hover:border-line-strong focus:border-accent outline-none font-semibold text-ink px-0 py-0 w-44 truncate"
                  :placeholder="`LAG ${g.id}`" />
                <span v-else class="font-semibold text-ink truncate">{{ names[g.id] || `LAG ${g.id}` }}</span>
                <Badge :tone="g.mode === 2 ? 'accent' : 'neutral'">{{ g.mode === 2 ? t('lag.lacp') : t('lag.static') }}</Badge>
              </div>
              <p class="hint">{{ g.ports.length === 1 ? t('lag.memberOne') : t('lag.members', { n: g.ports.length }) }} · {{ g.ports.reduce((s, p) => s + (p.port >= 9 ? 10 : 2.5), 0) }}G</p>
            </div>
          </div>
          <Btn v-if="can('lag')" variant="ghost" size="sm" icon="trash" icon-only :aria-label="t('common.remove')" class="hover:text-danger" @click="removeGroup(g.id)" />
        </div>
        <div class="px-4 py-3 flex gap-2 flex-wrap">
          <div v-for="p in g.ports" :key="p.port" class="flex-1 min-w-[72px] rounded-lg border p-2.5 text-center" :class="p.state === 1 ? 'border-ok/50 bg-ok-soft' : 'border-line bg-surface-2'">
            <div class="text-sm font-semibold" :class="p.state === 1 ? 'text-ok-ink' : 'text-muted'">{{ p.port >= 9 ? 'SFP+' : 'P' }}{{ p.port }}</div>
            <div class="text-[10px] mt-0.5" :class="p.state === 1 ? 'text-ok' : 'text-faint'">{{ p.state === 1 ? t('lag.active') : t('ports.down') }}</div>
            <div v-if="g.mode === 2" class="text-[10px] text-muted mt-0.5">{{ p.timeout === 0 ? t('lag.fast') : t('lag.slow') }}</div>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="card">
      <EmptyState icon="lag" :title="loadError ? t('common.failedLoad') : t('lag.noGroups')" :text="loadError || t('lag.createDesc')">
        <Btn v-if="loadError" size="sm" icon="refresh" @click="load">{{ t('ui.retry') }}</Btn>
        <Btn v-else-if="can('lag')" variant="primary" icon="plus" @click="openCreate">{{ t('lag.create') }}</Btn>
      </EmptyState>
    </div>

    <div class="card card-body flex items-center gap-4 flex-wrap">
      <div class="flex-1 min-w-[200px]">
        <h3 class="h2">{{ t('lag.priority') }}</h3><p class="hint">{{ t('lag.priorityDesc') }}</p>
      </div>
      <input v-model.number="systemPriority" type="number" min="1" max="65535" :disabled="!can('lag')" class="input input-sm num w-28" />
      <Btn v-if="can('lag')" size="sm" @click="applyPriority">{{ t('lag.save') }}</Btn>
    </div>

    <!-- Create -->
    <Modal :open="modal" :title="t('lag.create')" @close="modal = false">
      <div class="space-y-4">
        <div>
          <label class="label" for="lag-name">{{ t('lag.name') }}</label>
          <input id="lag-name" v-model.trim="draft.name" maxlength="64" class="input" :placeholder="t('lag.namePlaceholder')" autofocus />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="label" for="lag-group">{{ t('lag.groupNum') }}</label>
            <select id="lag-group" v-model.number="draft.id" class="select"><option v-for="n in availableGroupIds" :key="n" :value="n">LAG {{ n }}</option></select>
          </div>
          <div v-if="draft.mode === 2">
            <label class="label" for="lag-timeout">{{ t('lag.timeout') }}</label>
            <select id="lag-timeout" v-model.number="draft.timeout" class="select"><option :value="0">{{ t('lag.timeoutShort') }}</option><option :value="1">{{ t('lag.timeoutLong') }}</option></select>
          </div>
        </div>
        <div role="group" aria-labelledby="lag-mode-label">
          <span id="lag-mode-label" class="label">{{ t('lag.mode') }}</span>
          <div class="grid grid-cols-2 gap-2">
            <button v-for="m in [2, 1]" :key="m" type="button" @click="draft.mode = m" :aria-pressed="draft.mode === m" class="rounded-lg border-2 p-3 text-start transition" :class="draft.mode === m ? 'border-accent bg-accent-soft' : 'border-line hover:border-line-strong'">
              <div class="text-sm font-semibold" :class="draft.mode === m ? 'text-accent-ink' : 'text-ink'">{{ m === 2 ? t('lag.lacp') : t('lag.static') }}</div>
              <div class="hint mt-0.5">{{ m === 2 ? t('lag.lacpDesc') : t('lag.staticDesc') }}</div>
            </button>
          </div>
        </div>
        <div role="group" aria-labelledby="lag-ports-label">
          <span id="lag-ports-label" class="label">{{ t('lag.selectPorts') }}</span>
          <div class="grid grid-cols-5 gap-2">
            <button v-for="p in availablePorts" :key="p.port" type="button" @click="togglePort(p.port)" :aria-pressed="draft.ports.includes(p.port)" class="rounded-lg border-2 py-2 text-center text-xs font-semibold transition"
              :class="draft.ports.includes(p.port) ? 'border-accent bg-accent-soft text-accent-ink' : 'border-line text-muted hover:border-line-strong'">
              {{ p.port >= 9 ? 'SFP+' : 'P' }}{{ p.port }}
              <div class="text-[10px] font-normal opacity-70">{{ p.port >= 9 ? '10G' : '2.5G' }}</div>
            </button>
          </div>
          <p v-if="draft.ports.length < 2" class="hint mt-2">{{ t('lag.minPorts') }}</p>
          <p v-if="mixedMedia" class="text-xs text-warn-ink bg-warn-soft px-3 py-2 rounded-lg mt-2">{{ t('lag.mixedMedia') }}</p>
          <p v-if="draft.ports.includes(1)" class="text-xs text-warn-ink bg-warn-soft px-3 py-2 rounded-lg mt-2">{{ t('lag.mgmtWarn') }}</p>
        </div>
      </div>
      <template #footer>
        <Btn @click="modal = false">{{ t('common.cancel') }}</Btn>
        <Btn variant="primary" :disabled="draft.ports.length < 2" :loading="applying" @click="createGroup">{{ t('vlans.create') }}</Btn>
      </template>
    </Modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '../composables/useApi.js'
import { useToast } from '../composables/useToast.js'
import { useConfirm } from '../composables/useConfirm.js'
import { useAuthStore } from '../stores/auth.js'
import { useSwitchesStore } from '../stores/switches.js'
import { useI18n } from '../i18n/index.js'
import Btn from '../components/ui/Btn.vue'
import Badge from '../components/ui/Badge.vue'
import Modal from '../components/ui/Modal.vue'
import EmptyState from '../components/ui/EmptyState.vue'

const props = defineProps({ switchId: Number })
const { t } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()
const sw = useSwitchesStore()
// admin and the setting is changeable on this switch's firmware (2.0.0.x: see read_only from the backend)
const can = (feature) => auth.isAdmin && !sw.readOnly(feature)

const allPorts = ref([])
const names = ref({})
const savedNames = ref({})
const systemPriority = ref(32768)
const modal = ref(false)
const applying = ref(false)
const loadError = ref('')
const draft = reactive({ id: 1, name: '', mode: 2, timeout: 0, ports: [] })

const groups = computed(() => {
  const map = {}
  allPorts.value.filter(p => p.group > 0 && p.type > 0).forEach(p => {
    if (!map[p.group]) map[p.group] = { id: p.group, mode: p.type, ports: [], allUp: true }
    map[p.group].ports.push(p)
    if (p.state !== 1) map[p.group].allUp = false
  })
  return Object.values(map).sort((a, b) => a.id - b.id)
})
const usedPorts = computed(() => new Set(allPorts.value.filter(p => p.group > 0 && p.type > 0).map(p => p.port)))
const availablePorts = computed(() => allPorts.value.filter(p => !usedPorts.value.has(p.port)))
const availableGroupIds = computed(() => { const used = new Set(groups.value.map(g => g.id)); return Array.from({ length: 15 }, (_, i) => i + 1).filter(i => !used.has(i)) })
const mixedMedia = computed(() => draft.ports.some(p => p >= 9) && draft.ports.some(p => p < 9))

function togglePort(port) { const i = draft.ports.indexOf(port); i >= 0 ? draft.ports.splice(i, 1) : draft.ports.push(port) }

async function load() {
  try {
    const data = await api(`/api/switches/${props.switchId}/lag`)
    systemPriority.value = Number(data.system_priority) || 32768
    allPorts.value = data.ports
    names.value = { ...(data.group_names || {}) }
    savedNames.value = { ...(data.group_names || {}) }
    loadError.value = ''
  } catch (e) { loadError.value = e.message }
}

function openCreate() {
  Object.assign(draft, { id: availableGroupIds.value[0] || 1, name: '', mode: 2, timeout: 0, ports: [] })
  modal.value = true
}

function rowsPayload(mapper) {
  return allPorts.value.map(p => ({ port: p.port, type: p.type, timeout: p.timeout, priority: p.priority ?? 128, group: p.group, ...(mapper(p) || {}) }))
}

async function createGroup() {
  applying.value = true
  try {
    const ports = rowsPayload(p => draft.ports.includes(p.port) ? { type: draft.mode, group: draft.id, timeout: draft.timeout } : null)
    const group_names = { ...savedNames.value, [draft.id]: draft.name || `LAG ${draft.id}` }
    await api(`/api/switches/${props.switchId}/lag`, { method: 'POST', body: JSON.stringify({ system_priority: systemPriority.value, ports, group_names }) })
    modal.value = false
    toast.success(t('lag.created'))
    await load()
  } catch (e) { toast.error(e.message) }
  finally { applying.value = false }
}

async function removeGroup(id) {
  if (!await confirm({ title: t('common.remove'), message: t('lag.removeConfirm', { id }), danger: true, confirmText: t('common.remove') })) return
  try {
    const ports = rowsPayload(p => p.group === id ? { type: 0, group: 0, timeout: 0 } : null)
    await api(`/api/switches/${props.switchId}/lag`, { method: 'POST', body: JSON.stringify({ system_priority: systemPriority.value, ports }) })
    toast.success(t('lag.removed'))
    await load()
  } catch (e) { toast.error(e.message) }
}

async function rename(id) {
  if ((names.value[id] || '') === (savedNames.value[id] || '')) return
  try {
    const res = await api(`/api/switches/${props.switchId}/lag/names`, { method: 'PUT', body: JSON.stringify({ group_names: { [id]: names.value[id] || `LAG ${id}` } }) })
    savedNames.value = { ...res.group_names }
    toast.success(t('lag.renamed'))
  } catch (e) { toast.error(e.message) }
}

async function applyPriority() {
  try {
    await api(`/api/switches/${props.switchId}/lag`, { method: 'POST', body: JSON.stringify({ system_priority: systemPriority.value, ports: rowsPayload(() => null) }) })
    toast.success(t('lag.priorityUpdated'))
  } catch (e) { toast.error(e.message) }
}

onMounted(load)
</script>
