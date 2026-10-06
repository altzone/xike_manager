<template>
  <div class="space-y-5">
    <div class="card overflow-hidden">
      <div class="card-head items-center flex-wrap gap-3">
        <div>
          <h3 class="h2 inline-flex items-center gap-1.5">{{ t('mac.title') }} <Tip :title="t('mac.title')" :text="t('mac.tip')" /></h3>
          <p class="hint">{{ total === 1 ? t('mac.entriesOne') : t('mac.entries', { count: total }) }}</p>
          <p v-if="truncated" class="text-xs text-warn-ink mt-0.5">{{ t('mac.truncated') }}</p>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <div class="relative">
            <Icon name="search" :size="15" class="absolute start-3 top-1/2 -translate-y-1/2 text-faint pointer-events-none" />
            <input v-model="search" @input="debouncedSearch" :placeholder="t('mac.search')" class="input input-sm ps-9 w-56" maxlength="32" />
          </div>
          <Btn size="sm" icon="refresh" icon-only :aria-label="t('ui.refresh')" :loading="loading" @click="refresh" />
          <Btn v-if="can('mac_table')" size="sm" variant="danger-soft" icon="trash" @click="clearMacs">{{ t('mac.clearAll') }}</Btn>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table v-if="macs.length" class="table">
          <thead><tr>
            <th>#</th><th>{{ t('sys.macAddress') }}</th><th>{{ t('mac.vendor') }}</th><th>{{ t('mac.port') }}</th><th>{{ v2 ? 'VLAN' : t('mac.vlanGroup') }}</th><th class="!text-end">{{ t('mac.age') }}</th>
          </tr></thead>
          <tbody>
            <tr v-for="m in macs" :key="m.idx + m.mac">
              <td class="text-muted num">{{ m.idx }}</td>
              <td class="mono text-ink font-medium">{{ m.mac }}</td>
              <td><span v-if="m.vendor" class="text-ink-2">{{ m.vendor }}</span><span v-else class="text-faint">{{ t('mac.unknown') }}</span></td>
              <!-- port 0: the switch's own address (its CPU port) -->
              <td><Badge v-if="m.port === 0" tone="neutral">{{ t('mac.cpu') }}</Badge><Badge v-else :tone="m.port >= 9 ? 'sfp' : 'accent'">{{ t('mac.port') }} {{ m.port }}</Badge></td>
              <td class="num text-ink-2">{{ v2 ? (m.vlan ?? m.fid) : m.fid }}</td>
              <td class="num text-end text-muted">{{ m.age }}</td>
            </tr>
          </tbody>
        </table>
        <EmptyState v-else compact icon="mac" :title="loadError ? t('common.failedLoad') : (search ? t('mac.noMatch') : t('mac.empty'))" :text="loadError" />
      </div>
    </div>

    <!-- Static entries -->
    <div class="card overflow-hidden">
      <div class="card-head">
        <div><h3 class="h2">{{ t('sys.staticMac') }}</h3><p class="hint">{{ t('sys.staticMacTip') }}</p></div>
      </div>
      <form v-if="can('static_mac')" @submit.prevent="addStatic" class="px-5 py-4 grid grid-cols-1 md:grid-cols-[1fr_160px_160px_auto] gap-3 items-end border-b border-line" novalidate>
        <div><label class="label" for="static-mac">{{ t('sys.macAddress') }}</label><input id="static-mac" v-model.trim="draft.mac" class="input input-sm mono" placeholder="AA:BB:CC:DD:EE:FF" pattern="^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$" required /></div>
        <div><label class="label" for="static-port">{{ t('sys.macPort') }}</label><select id="static-port" v-model.number="draft.port" class="select select-sm"><option v-for="p in 10" :key="p" :value="p">{{ t('mac.port') }} {{ p }}{{ p >= 9 ? ' (SFP+)' : '' }}</option></select></div>
        <!-- 2.0.0.x keys static entries by VLAN ID (1-4094), 1.0.0.x by VLAN group (FID 0-63) -->
        <div v-if="v2"><label class="label" for="static-vlan">{{ t('sys.macVlanId') }}</label><input id="static-vlan" v-model.number="draft.vlan" type="number" min="1" max="4094" class="input input-sm num" /></div>
        <div v-else><label class="label" for="static-fid">{{ t('sys.macVlanGroup') }}</label><input id="static-fid" v-model.number="draft.fid" type="number" min="0" max="63" class="input input-sm num" /></div>
        <Btn type="submit" variant="primary" size="sm" icon="plus" :loading="adding" :disabled="!macValid">{{ t('sys.macAdd') }}</Btn>
      </form>
      <div class="overflow-x-auto">
        <table v-if="statics.length" class="table">
          <thead><tr><th>{{ t('sys.macAddress') }}</th><th>{{ t('mac.port') }}</th><th>{{ v2 ? 'VLAN' : t('mac.vlanGroup') }}</th><th v-if="can('static_mac')" class="w-12"></th></tr></thead>
          <tbody>
            <tr v-for="m in statics" :key="`${m.mac}-${m.port}-${m.vlan ?? m.fid}`">
              <td class="mono font-medium">{{ m.mac }}</td>
              <td><Badge :tone="m.port >= 9 ? 'sfp' : 'accent'">{{ t('mac.port') }} {{ m.port }}</Badge></td>
              <td class="num text-ink-2">{{ v2 ? (m.vlan ?? m.fid) : m.fid }}</td>
              <td v-if="can('static_mac')" class="text-end"><Btn variant="ghost" size="xs" icon="trash" icon-only :aria-label="t('common.delete')" class="hover:text-danger" @click="deleteStatic(m)" /></td>
            </tr>
          </tbody>
        </table>
        <EmptyState v-else-if="staticsError" compact icon="x-circle" :title="t('common.failedLoad')" :text="staticsError">
          <Btn size="sm" icon="refresh" @click="loadStatics">{{ t('ui.retry') }}</Btn>
        </EmptyState>
        <EmptyState v-else compact icon="lock" :title="t('sys.macNone')" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../composables/useApi.js'
import { useToast } from '../composables/useToast.js'
import { useConfirm } from '../composables/useConfirm.js'
import { useAuthStore } from '../stores/auth.js'
import { useSwitchesStore } from '../stores/switches.js'
import { useI18n } from '../i18n/index.js'
import Tip from '../components/Tip.vue'
import Btn from '../components/ui/Btn.vue'
import Badge from '../components/ui/Badge.vue'
import Icon from '../components/ui/Icon.vue'
import EmptyState from '../components/ui/EmptyState.vue'

const props = defineProps({ switchId: Number })
const { t } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()
const sw = useSwitchesStore()
// admin and the setting is changeable on this switch's firmware (2.0.0.x: see read_only from the backend)
const can = (feature) => auth.isAdmin && !sw.readOnly(feature)
// 2.0.0.x: entries are keyed by VLAN ID instead of VLAN group (FID)
const v2 = computed(() => (sw.current?.firmware_line || 1) >= 2)

const macs = ref([])
const total = ref(0)
const truncated = ref(false)
const search = ref('')
const loading = ref(false)
const loadError = ref('')
const statics = ref([])
const staticsError = ref('')
const draft = reactive({ mac: '', port: 1, fid: 0, vlan: 1 })
const adding = ref(false)
const macValid = computed(() => /^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$/.test(draft.mac))
let timer = null
let seq = 0

async function loadMacs(query = '') {
  const my = ++seq
  loading.value = true
  try {
    const res = await api(`/api/switches/${props.switchId}/mac/dynamic${query ? `?search=${encodeURIComponent(query)}` : ''}`)
    if (my !== seq) return  // a newer request is in flight
    macs.value = res.entries || []
    total.value = res.total || macs.value.length
    truncated.value = !!res.truncated
    loadError.value = ''
  } catch (e) { if (my === seq) { loadError.value = e.message; macs.value = [] } }
  finally { if (my === seq) loading.value = false }
}
function debouncedSearch() { clearTimeout(timer); timer = setTimeout(() => loadMacs(search.value), 300) }
function refresh() { return loadMacs(search.value) }

async function clearMacs() {
  if (!await confirm({ title: t('mac.clearAll'), message: t('mac.clearConfirm'), danger: true, confirmText: t('mac.clearAll') })) return
  try { await api(`/api/switches/${props.switchId}/mac/clear`, { method: 'POST' }); await loadMacs() } catch (e) { toast.error(e.message) }
}

async function loadStatics() {
  try {
    statics.value = await api(`/api/switches/${props.switchId}/mac/static`)
    staticsError.value = ''
  } catch (e) { statics.value = []; staticsError.value = e.message }
}
async function addStatic() {
  if (!macValid.value) return
  adding.value = true
  try {
    const entry = v2.value ? { vlan_id: draft.vlan || 1 } : { fid: draft.fid || 0 }
    const res = await api(`/api/switches/${props.switchId}/mac/static/add`, { method: 'POST', body: JSON.stringify({ mac: draft.mac, port: draft.port, ...entry }) })
    toast.success(t('sys.macAdded'))
    for (const w of res.warnings || []) toast.error(w)
    draft.mac = ''
    await loadStatics()
  } catch (e) { toast.error(e.message) }
  finally { adding.value = false }
}
async function deleteStatic(m) {
  if (!await confirm({ title: t('common.delete'), message: t('mac.deleteStatic', { mac: m.mac }), danger: true, confirmText: t('common.delete') })) return
  try {
    const entry = v2.value ? { vlan_id: m.vlan ?? (Number(m.fid) || 1) } : { fid: m.fid }
    const res = await api(`/api/switches/${props.switchId}/mac/static/delete`, { method: 'POST', body: JSON.stringify({ mac: m.mac, port: m.port, ...entry }) })
    toast.success(t('mac.staticDeleted'))
    for (const w of res.warnings || []) toast.error(w)
    await loadStatics()
  } catch (e) { toast.error(e.message) }
}

onMounted(() => { loadMacs(); loadStatics() })
onUnmounted(() => clearTimeout(timer))
</script>
