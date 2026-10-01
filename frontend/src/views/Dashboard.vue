<template>
  <div class="space-y-6">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h2 class="text-xl font-semibold tracking-tight">{{ t('dash.title') }}</h2>
        <p class="hint mt-0.5">{{ t('dash.subtitle') }}</p>
      </div>
      <Btn v-if="auth.isAdmin" variant="primary" icon="plus" @click="openAdd">{{ t('dash.addSwitch') }}</Btn>
    </div>

    <div v-if="sw.list.length" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <div v-for="s in sw.list" :key="s.id" class="card flex flex-col group hover:border-accent/50 transition-colors">
        <router-link :to="`/switch/${s.id}`" class="p-5 flex-1 block focus-visible:outline-accent rounded-t-[var(--radius-card)]">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <h3 class="font-semibold text-ink truncate group-hover:text-accent transition-colors">{{ s.name }}</h3>
              <p class="mono text-muted mt-0.5">{{ s.ip }}</p>
            </div>
            <span class="w-10 h-10 rounded-lg bg-accent-soft text-accent flex items-center justify-center shrink-0"><Icon name="switch" :size="20" /></span>
          </div>
          <div class="mt-4 flex items-center gap-2 flex-wrap">
            <Badge v-if="ping[s.id]" :tone="ping[s.id].online ? 'ok' : 'danger'" dot>{{ ping[s.id].online ? t('sw.online') : t('sw.offline') }}</Badge>
            <Badge v-else tone="neutral" dot>{{ t('common.loading') }}</Badge>
            <Badge v-if="ping[s.id]?.online && ping[s.id].temperature" tone="neutral">{{ ping[s.id].temperature }}°C</Badge>
            <Badge v-if="s.swap_sfp_9_10" tone="sfp" :title="t('sys.portMapSwap')">SFP+ 9⇄10</Badge>
          </div>
          <dl class="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <dt class="text-muted">{{ t('swdash.model') }}</dt><dd class="text-ink-2 truncate text-end">{{ s.model || '—' }}</dd>
            <dt class="text-muted">{{ t('dash.firmware') }}</dt><dd class="text-ink-2 mono text-end">{{ s.firmware || '—' }}</dd>
            <dt class="text-muted">MAC</dt><dd class="text-ink-2 mono text-end truncate">{{ s.mac_address || '—' }}</dd>
          </dl>
        </router-link>
        <div class="px-3 py-2 border-t border-line flex items-center justify-between">
          <Btn tag="router-link" :to="`/switch/${s.id}`" variant="link" size="sm" icon="chevron-right">{{ t('dash.open') }}</Btn>
          <div v-if="auth.isAdmin" class="flex gap-1">
            <Btn variant="ghost" size="sm" icon="pencil" icon-only :aria-label="t('common.edit')" @click="openEdit(s)" />
            <Btn variant="ghost" size="sm" icon="trash" icon-only :aria-label="t('common.remove')" class="hover:text-danger" @click="remove(s)" />
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="sw.loaded" class="card">
      <EmptyState icon="switch" :title="t('dash.noSwitches')" :text="t('dash.addFirstHint')">
        <Btn v-if="auth.isAdmin" variant="primary" icon="plus" @click="openAdd">{{ t('dash.addFirst') }}</Btn>
      </EmptyState>
    </div>

    <!-- Add / edit modal -->
    <Modal :open="modal" :title="editing ? t('dash.editSwitch') : t('dash.addSwitch')" @close="modal = false">
      <form @submit.prevent="save" class="space-y-3" novalidate id="switch-form">
        <div>
          <label class="label">{{ t('dash.name') }}</label>
          <input v-model.trim="form.name" required class="input" placeholder="Core switch" autofocus />
        </div>
        <div>
          <label class="label">{{ t('dash.ip') }}</label>
          <input v-model.trim="form.ip" required class="input mono" placeholder="192.168.1.10" />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="label">{{ t('dash.username') }}</label>
            <input v-model.trim="form.username" required class="input" autocomplete="off" />
          </div>
          <div>
            <label class="label">{{ t('dash.password') }}</label>
            <input v-model="form.password" type="password" :required="!editing" class="input" autocomplete="new-password" :placeholder="editing ? t('dash.passwordKeep') : ''" />
          </div>
        </div>
        <label v-if="!editing" class="flex items-start gap-2.5 text-sm cursor-pointer pt-1">
          <input type="checkbox" v-model="form.swap_sfp_9_10" class="mt-1 accent-accent">
          <span><span class="text-ink-2">{{ t('dash.swapSfp') }}</span><span class="block hint">{{ t('dash.swapSfpHint') }}</span></span>
        </label>
        <p v-if="formError" class="text-sm text-danger-ink bg-danger-soft rounded-lg px-3 py-2" role="alert">{{ formError }}</p>
      </form>
      <template #footer>
        <Btn @click="modal = false">{{ t('common.cancel') }}</Btn>
        <Btn variant="primary" type="submit" form="switch-form" :loading="saving">{{ saving ? t('dash.testing') : (editing ? t('common.save') : t('dash.add')) }}</Btn>
      </template>
    </Modal>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { api } from '../composables/useApi.js'
import { useToast } from '../composables/useToast.js'
import { useConfirm } from '../composables/useConfirm.js'
import { useAuthStore } from '../stores/auth.js'
import { useSwitchesStore } from '../stores/switches.js'
import { useI18n } from '../i18n/index.js'
import Btn from '../components/ui/Btn.vue'
import Badge from '../components/ui/Badge.vue'
import Icon from '../components/ui/Icon.vue'
import Modal from '../components/ui/Modal.vue'
import EmptyState from '../components/ui/EmptyState.vue'

const { t } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()
const sw = useSwitchesStore()

const ping = ref({})
const modal = ref(false)
const editing = ref(null)
const saving = ref(false)
const formError = ref('')
const form = reactive({ name: '', ip: '', username: 'admin', password: 'admin', swap_sfp_9_10: false })

async function load() {
  try {
    await sw.load()
    await Promise.all(sw.list.map(async (s) => {
      try { ping.value[s.id] = await api(`/api/switches/${s.id}/ping`) } catch (e) { ping.value[s.id] = { online: false } }
    }))
  } catch (e) { toast.error(e.message) }
}

function openAdd() {
  editing.value = null
  Object.assign(form, { name: '', ip: '', username: 'admin', password: 'admin', swap_sfp_9_10: false })
  formError.value = ''
  modal.value = true
}
function openEdit(s) {
  editing.value = s
  Object.assign(form, { name: s.name, ip: s.ip, username: s.username || 'admin', password: '', swap_sfp_9_10: !!s.swap_sfp_9_10 })
  formError.value = ''
  modal.value = true
}

async function save() {
  saving.value = true
  formError.value = ''
  try {
    if (editing.value) {
      const body = { name: form.name, ip: form.ip, username: form.username }
      if (form.password) body.password = form.password
      const updated = await api(`/api/switches/${editing.value.id}`, { method: 'PUT', body: JSON.stringify(body) })
      sw.patch(editing.value.id, updated)
      toast.success(t('dash.updated'))
    } else {
      await api('/api/switches', { method: 'POST', body: JSON.stringify(form) })
      toast.success(t('dash.added'))
    }
    modal.value = false
    await load()
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function remove(s) {
  if (!await confirm({ title: t('common.remove'), message: t('dash.deleteConfirm', { name: s.name }), danger: true, confirmText: t('common.remove') })) return
  try {
    await api(`/api/switches/${s.id}`, { method: 'DELETE' })
    toast.success(t('dash.deleted'))
    await load()
  } catch (e) { toast.error(e.message) }
}

onMounted(load)
</script>
