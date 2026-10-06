<template>
  <div class="space-y-5">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <p class="hint max-w-2xl">{{ t('vlans.tip') }}</p>
      <div class="flex items-center gap-2 shrink-0">
        <Badge tone="neutral"><span class="inline-flex items-center gap-1">{{ t('vlans.tagEntries', { used: limits.used, max: limits.max }) }} <Tip :text="t('vlans.tagTip')" /></span></Badge>
        <Badge tone="warn"><span class="inline-flex items-center gap-1">{{ t('vlans.nativeMax') }} <Tip :text="t('vlans.nativeTip')" /></span></Badge>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-[340px_1fr] gap-5 items-start">
      <!-- VLAN list -->
      <div class="card">
        <div class="card-head">
          <div><h3 class="h2">{{ t('vlans.networks') }}</h3><p class="hint">{{ t('vlans.networksDesc') }}</p></div>
          <Btn v-if="auth.isAdmin" variant="primary" size="sm" icon="plus" @click="openAdd()">{{ t('vlans.addVlan') }}</Btn>
        </div>
        <ul v-if="vlans.length" class="divide-y divide-line">
          <li v-for="v in vlans" :key="v.vlan_id" class="px-4 py-2.5 flex items-center gap-3 group">
            <span class="w-11 h-9 rounded-md flex items-center justify-center text-sm font-semibold num shrink-0" :class="v.vlan_id <= 63 ? 'bg-accent-soft text-accent-ink' : 'bg-surface-3 text-muted'">{{ v.vlan_id }}</span>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-medium truncate" :class="v.defined ? 'text-ink' : 'text-muted italic'">{{ v.defined ? v.name : t('vlans.unnamed') }}</p>
              <p class="text-[11px] text-muted flex items-center gap-1.5">
                <span v-if="v.in_use" class="text-ok-ink">{{ t('vlans.inUse') }}</span>
                <span v-if="v.in_use && v.vlan_id > 63" aria-hidden="true">·</span>
                <span v-if="v.vlan_id > 63" :title="t('vlans.vlanIdWarn', { id: v.vlan_id })">{{ t('vlans.trunkOnly') }}</span>
              </p>
            </div>
            <div v-if="auth.isAdmin" class="flex gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition">
              <Btn variant="ghost" size="xs" icon="pencil" icon-only :aria-label="t('common.edit')" @click="openAdd(v)" />
              <Btn v-if="v.defined" variant="ghost" size="xs" icon="trash" icon-only :aria-label="t('common.delete')" class="hover:text-danger" @click="deleteVlan(v)" />
            </div>
          </li>
        </ul>
        <EmptyState v-else compact icon="vlans" :title="t('vlans.noVlans')" />
        <div v-if="auth.isAdmin && vlans.some(v => v.defined)" class="px-4 py-3 border-t border-line">
          <Btn size="sm" icon="refresh" block :loading="syncing" @click="syncVlans">{{ t('vlans.sync') }}</Btn>
        </div>
      </div>

      <!-- Port assignment -->
      <div class="card overflow-hidden">
        <div class="card-head">
          <div><h3 class="h2">{{ t('vlans.portAssign') }}</h3><p class="hint">{{ t('vlans.portAssignDesc') }}</p></div>
          <Badge v-if="dirty" tone="warn" dot>{{ t('vlans.changedPorts', { n: changed.length }) }}</Badge>
          <Badge v-else-if="auth.isAdmin && sw.readOnly('vlans')" :title="t('v2.readOnlyTip')"><Icon name="lock" :size="12" /> {{ t('v2.readOnly') }}</Badge>
        </div>
        <div class="overflow-x-auto">
          <table class="table">
            <thead>
              <tr>
                <th>{{ t('ports.port') }}</th>
                <th><span class="inline-flex items-center gap-1">{{ t('vlans.mode') }} <Tip :title="t('vlans.mode')" :text="t('vlans.modeTip')" /></span></th>
                <th><span class="inline-flex items-center gap-1">{{ t('vlans.pvid') }} <Tip :title="t('vlans.pvid')" :text="t('vlans.pvidTip')" /></span></th>
                <th><span class="inline-flex items-center gap-1">{{ t('vlans.allowed') }} <Tip :title="t('vlans.allowed')" :text="t('vlans.allowedTip')" /></span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.port" :class="isChanged(r) ? 'bg-warn-soft/40' : ''">
                <td>
                  <div class="flex items-center gap-2">
                    <span class="font-semibold w-5">{{ r.port }}</span>
                    <Badge :tone="r.port >= 9 ? 'sfp' : 'rj45'"><bdi dir="ltr">{{ r.port >= 9 ? 'SFP+' : 'RJ45' }}</bdi></Badge>
                    <Badge v-if="r.port === 1" tone="warn">{{ t('vlans.mgmt') }}</Badge>
                  </div>
                </td>
                <td>
                  <select v-model="r.mode" @change="onModeChange(r)" :disabled="!editable(r)" class="select select-sm w-28">
                    <option v-if="r.mode === 'unknown'" value="unknown" disabled>{{ t('vlans.modeUnknown') }}</option>
                    <option value="flat">{{ t('vlans.flat') }}</option>
                    <option value="access">{{ t('vlans.access') }}</option>
                    <option value="trunk">{{ t('vlans.trunk') }}</option>
                  </select>
                </td>
                <td>
                  <select v-if="r.mode === 'access'" v-model.number="r.access_vlan" :disabled="!editable(r)" class="select select-sm w-44">
                    <option v-for="v in pvidVlans" :key="v.vlan_id" :value="v.vlan_id">{{ v.name }} ({{ v.vlan_id }})</option>
                  </select>
                  <select v-else-if="r.mode === 'trunk'" v-model.number="r.native_vlan" :disabled="!editable(r)" class="select select-sm w-44">
                    <option :value="0">{{ t('vlans.defaultBridge') }}</option>
                    <option v-for="v in pvidVlans" :key="v.vlan_id" :value="v.vlan_id">{{ v.name }} ({{ v.vlan_id }})</option>
                  </select>
                  <span v-else class="text-faint">—</span>
                </td>
                <td>
                  <div v-if="r.mode === 'trunk'" class="flex flex-wrap gap-1.5">
                    <label v-for="v in vlans" :key="v.vlan_id" class="chip cursor-pointer select-none transition border has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-surface"
                      :class="[r.trunk_vlans.includes(v.vlan_id) ? 'bg-accent-soft border-accent/40 text-accent-ink' : 'bg-surface-2 border-line text-muted hover:border-line-strong', !editable(r) ? 'opacity-60 cursor-not-allowed' : '']">
                      <input type="checkbox" :value="v.vlan_id" v-model="r.trunk_vlans" :disabled="!editable(r)" class="sr-only">
                      {{ v.name }} <span class="opacity-60 num">{{ v.vlan_id }}</span>
                    </label>
                    <span v-if="!vlans.length" class="text-faint">—</span>
                  </div>
                  <span v-else class="text-faint">—</span>
                </td>
              </tr>
              <tr v-if="!rows.length && !loadError"><td colspan="4" class="text-center text-muted py-8">{{ t('common.loading') }}</td></tr>
              <tr v-if="loadError"><td colspan="4"><EmptyState compact icon="x-circle" :title="t('common.failedLoad')" :text="loadError"><Btn size="sm" icon="refresh" @click="load">{{ t('ui.retry') }}</Btn></EmptyState></td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Unsaved changes bar -->
    <Teleport to="body">
      <transition name="banner">
        <div v-if="dirty" class="fixed bottom-0 inset-x-0 lg:start-60 z-[70] px-4 pb-4 pointer-events-none">
          <div class="pointer-events-auto mx-auto max-w-3xl rounded-xl bg-side text-side-ink shadow-[var(--shadow-pop)] border border-side-line px-4 py-3 flex items-center gap-3">
            <Icon name="warning" :size="18" class="text-warn shrink-0" />
            <span class="text-sm flex-1">{{ t('vlans.unsaved') }} · {{ t('vlans.changedPorts', { n: changed.length }) }}</span>
            <Btn variant="ghost" size="sm" class="text-side-muted hover:text-white hover:bg-side-2" :disabled="applying" @click="discard">{{ t('vlans.discard') }}</Btn>
            <Btn variant="primary" size="sm" :loading="applying" @click="applyAll">{{ t('vlans.applySave') }}</Btn>
          </div>
        </div>
      </transition>
    </Teleport>

    <!-- Add / rename VLAN -->
    <Modal :open="modal" :title="editVlan ? t('vlans.vlanName') : t('vlans.createVlan')" width="sm" @close="modal = false">
      <form id="vlan-form" @submit.prevent="saveVlan" class="space-y-3" novalidate>
        <div>
          <label class="label" for="vlan-form-id">{{ t('vlans.vlanId') }}</label>
          <input id="vlan-form-id" v-model.number="form.id" type="number" min="1" max="4094" required :disabled="!!editVlan" class="input num" placeholder="10" autofocus />
        </div>
        <div>
          <label class="label" for="vlan-form-name">{{ t('vlans.vlanName') }}</label>
          <input id="vlan-form-name" v-model.trim="form.name" required maxlength="64" class="input" :placeholder="t('vlans.namePlaceholder')" />
        </div>
        <p v-if="form.id > 63" class="text-xs text-warn-ink bg-warn-soft px-3 py-2 rounded-lg">{{ t('vlans.vlanIdWarn', { id: form.id }) }}</p>
        <p v-if="formError" class="text-sm text-danger-ink bg-danger-soft rounded-lg px-3 py-2" role="alert">{{ formError }}</p>
      </form>
      <template #footer>
        <Btn @click="modal = false">{{ t('common.cancel') }}</Btn>
        <Btn variant="primary" type="submit" form="vlan-form" :disabled="!form.id || !form.name">{{ editVlan ? t('common.save') : t('vlans.create') }}</Btn>
      </template>
    </Modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { api } from '../composables/useApi.js'
import { useToast } from '../composables/useToast.js'
import { useConfirm } from '../composables/useConfirm.js'
import { useAuthStore } from '../stores/auth.js'
import { useSwitchesStore } from '../stores/switches.js'
import { useI18n } from '../i18n/index.js'
import Tip from '../components/Tip.vue'
import Badge from '../components/ui/Badge.vue'
import Btn from '../components/ui/Btn.vue'
import Icon from '../components/ui/Icon.vue'
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

const vlans = ref([])
const rows = ref([])
const baseline = ref([])   // deep copies of the rows as loaded from the switch
const original = ref({})   // normalized baseline per port, for change detection
const limits = reactive({ used: 0, max: 111 })
const loadError = ref('')
const applying = ref(false)
const syncing = ref(false)
const modal = ref(false)
const editVlan = ref(null)
const form = reactive({ id: '', name: '' })
const formError = ref('')

const pvidVlans = computed(() => vlans.value.filter(v => v.vlan_id <= 63))
function editable(r) { return can('vlans') && r.port !== 1 && !applying.value }
const clone = x => JSON.parse(JSON.stringify(x))

function norm(r) {
  return JSON.stringify({ m: r.mode, a: r.mode === 'access' ? r.access_vlan : null, n: r.mode === 'trunk' ? r.native_vlan : null, t: r.mode === 'trunk' ? [...r.trunk_vlans].sort((a, b) => a - b) : [] })
}
function isChanged(r) { return original.value[r.port] !== undefined && norm(r) !== original.value[r.port] }
const changed = computed(() => rows.value.filter(isChanged))
const dirty = computed(() => changed.value.length > 0)

function toRow(a) {
  // the switch-reported mode is kept as is ('unknown' included) so that choosing another mode counts as a change
  return { port: a.port, mode: a.mode, access_vlan: a.mode === 'access' ? a.pvid : null,
           native_vlan: a.mode === 'trunk' ? a.pvid : null, trunk_vlans: [...(a.trunk_vlans || [])] }
}
function setBaseline(list) {
  baseline.value = clone(list)
  rows.value = clone(list)
  original.value = Object.fromEntries(list.map(r => [r.port, norm(r)]))
}

// VLAN list + limits only: safe to call while port rows have unsaved edits
async function loadVlans() {
  const [vl, lim] = await Promise.all([
    api(`/api/switches/${props.switchId}/vlans`),
    api(`/api/switches/${props.switchId}/vlans/limits`),
  ])
  vlans.value = vl
  limits.used = lim.used_tag_entries; limits.max = lim.max_tag_entries
}
// Port rows: replaces the rows and their baseline
async function loadRows() {
  const assignments = await api(`/api/switches/${props.switchId}/vlans/assignments`)
  setBaseline(assignments.map(toRow))
}
async function load() {
  try {
    await Promise.all([loadVlans(), loadRows()])
    loadError.value = ''
  } catch (e) { loadError.value = e.message; toast.error(e.message) }
}

function onModeChange(r) {
  if (r.mode === 'access' && !r.access_vlan) r.access_vlan = pvidVlans.value[0]?.vlan_id || 1
  if (r.mode === 'trunk' && r.native_vlan == null) r.native_vlan = 0   // default bridge: always offered by the select
}

// Restore the rows from the kept baseline, no network round trip needed
function discard() { if (!applying.value) rows.value = clone(baseline.value) }

async function applyAll() {
  applying.value = true
  try {
    const payload = changed.value.filter(r => r.mode !== 'unknown').map(r => ({
      port: r.port, mode: r.mode,
      access_vlan: r.mode === 'access' ? r.access_vlan : null,
      native_vlan: r.mode === 'trunk' ? r.native_vlan : null,
      trunk_vlans: r.mode === 'trunk' ? r.trunk_vlans : null,
    }))
    const res = await api(`/api/switches/${props.switchId}/vlans/apply`, { method: 'POST', body: JSON.stringify(payload) })
    toast.success(t('vlans.applied', { ports: res.port_vlans, tags: res.tag_entries }))
    for (const w of res.warnings || []) toast.error(w)
    await load()
  } catch (e) { toast.error(e.message) }
  finally { applying.value = false }
}

function openAdd(v = null) {
  editVlan.value = v
  form.id = v ? v.vlan_id : ''
  form.name = v && v.defined ? v.name : ''
  formError.value = ''
  modal.value = true
}
async function saveVlan() {
  formError.value = ''
  try {
    if (editVlan.value?.defined) await api(`/api/switches/${props.switchId}/vlans/${form.id}`, { method: 'PUT', body: JSON.stringify({ name: form.name }) })
    else await api(`/api/switches/${props.switchId}/vlans`, { method: 'POST', body: JSON.stringify({ vlan_id: form.id, name: form.name }) })
  } catch (e) { formError.value = e.message; return }
  modal.value = false
  await refreshVlans()
}
// After a VLAN is created/renamed/deleted only the list changes: keep the port rows and any unsaved edits
async function refreshVlans() {
  try { await loadVlans() } catch (e) { toast.error(e.message) }
}
async function deleteVlan(v) {
  const msg = t('vlans.deleteConfirm', { id: v.vlan_id }) + (v.in_use ? '\n' + t('vlans.deleteInUse', { id: v.vlan_id }) : '')
  if (!await confirm({ title: t('common.delete'), message: msg, danger: true, confirmText: t('common.delete') })) return
  try { await api(`/api/switches/${props.switchId}/vlans/${v.vlan_id}`, { method: 'DELETE' }) } catch (e) { toast.error(e.message); return }
  await refreshVlans()
}
async function syncVlans() {
  if (!await confirm({ title: t('vlans.sync'), message: t('vlans.syncConfirm') })) return
  syncing.value = true
  try {
    const res = await api(`/api/switches/${props.switchId}/vlans/sync`, { method: 'POST' })
    toast.success(t('vlans.synced', { targets: res.targets }))
  } catch (e) { toast.error(e.message) }
  finally { syncing.value = false }
}

onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  return await confirm({ title: t('vlans.unsaved'), message: t('vlans.leaveConfirm'), danger: true, confirmText: t('vlans.discard') })
})

// Refresh / tab close while edits are pending: let the browser ask (the in-app guard above covers navigation)
function onBeforeUnload(e) { e.preventDefault(); e.returnValue = '' }
watch(dirty, d => {
  if (d) window.addEventListener('beforeunload', onBeforeUnload)
  else window.removeEventListener('beforeunload', onBeforeUnload)
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))

onMounted(load)
</script>
