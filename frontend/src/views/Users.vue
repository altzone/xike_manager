<template>
  <div class="space-y-5">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <p class="hint">{{ t('users.subtitle') }}</p>
      <Btn variant="primary" icon="plus" @click="openAdd">{{ t('users.addUser') }}</Btn>
    </div>

    <div class="card overflow-hidden">
      <table class="table">
        <thead><tr><th>{{ t('users.username') }}</th><th>{{ t('users.role') }}</th><th>{{ t('users.created') }}</th><th class="!text-end">{{ t('users.actions') }}</th></tr></thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>
              <div class="flex items-center gap-2.5">
                <span class="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold" :class="u.role === 'admin' ? 'bg-accent-soft text-accent-ink' : 'bg-surface-3 text-muted'">{{ u.username[0]?.toUpperCase() }}</span>
                <span class="font-medium text-ink">{{ u.username }}</span>
                <Badge v-if="u.id === me" tone="neutral">{{ t('users.you') }}</Badge>
              </div>
            </td>
            <td>
              <select :value="u.role" @change="changeRole(u, $event)" :disabled="u.id === me || (u.role === 'admin' && adminCount <= 1)" class="select select-sm w-40"
                :title="u.id === me ? t('users.ownRole') : (u.role === 'admin' && adminCount <= 1 ? t('users.lastAdmin') : '')">
                <option value="admin">{{ t('users.roleAdmin') }}</option>
                <option value="viewer">{{ t('users.roleViewer') }}</option>
              </select>
            </td>
            <td class="text-muted num">{{ fmtDate(u.created_at) }}</td>
            <td class="text-end">
              <div class="flex gap-1 justify-end">
                <Btn size="xs" icon="key" @click="openReset(u)">{{ t('users.resetPw') }}</Btn>
                <Btn size="xs" variant="danger-soft" icon="trash" :disabled="u.id === me || (u.role === 'admin' && adminCount <= 1)" @click="deleteUser(u)">{{ t('users.delete') }}</Btn>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card card-body grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
      <div class="flex gap-3"><span class="w-8 h-8 rounded-lg bg-accent-soft text-accent flex items-center justify-center shrink-0"><Icon name="shield" :size="16" /></span>
        <div><p class="font-medium text-ink">{{ t('users.roleAdmin') }}</p><p class="hint">{{ t('users.roleAdminDesc') }}</p></div></div>
      <div class="flex gap-3"><span class="w-8 h-8 rounded-lg bg-surface-3 text-muted flex items-center justify-center shrink-0"><Icon name="eye" :size="16" /></span>
        <div><p class="font-medium text-ink">{{ t('users.roleViewer') }}</p><p class="hint">{{ t('users.roleViewerDesc') }}</p></div></div>
    </div>

    <Modal :open="showAdd" :title="t('users.addUser')" width="sm" @close="showAdd = false">
      <form id="user-form" @submit.prevent="addUser" class="space-y-3" novalidate>
        <div><label class="label">{{ t('users.username') }}</label><input v-model.trim="form.username" required maxlength="64" class="input" autofocus autocomplete="off" /></div>
        <div><label class="label">{{ t('login.password') }}</label><input v-model="form.password" type="password" required class="input" autocomplete="new-password" /><p class="hint mt-1">{{ t('setup.passwordHint') }}</p></div>
        <div><label class="label">{{ t('users.role') }}</label><select v-model="form.role" class="select"><option value="viewer">{{ t('users.roleViewer') }}</option><option value="admin">{{ t('users.roleAdmin') }}</option></select></div>
        <p v-if="error" class="text-sm text-danger-ink bg-danger-soft rounded-lg px-3 py-2" role="alert">{{ error }}</p>
      </form>
      <template #footer>
        <Btn @click="showAdd = false">{{ t('common.cancel') }}</Btn>
        <Btn variant="primary" type="submit" form="user-form" :disabled="!form.username || form.password.length < 6">{{ t('vlans.create') }}</Btn>
      </template>
    </Modal>

    <Modal :open="!!resetUser" :title="t('users.resetPw')" :subtitle="resetUser?.username" width="sm" @close="resetUser = null">
      <form id="reset-form" @submit.prevent="doReset" class="space-y-3" novalidate>
        <div><label class="label">{{ t('users.newPw') }}</label><input v-model="newPassword" type="password" required class="input" autofocus autocomplete="new-password" /><p class="hint mt-1">{{ t('setup.passwordHint') }}</p></div>
        <p v-if="error" class="text-sm text-danger-ink bg-danger-soft rounded-lg px-3 py-2" role="alert">{{ error }}</p>
      </form>
      <template #footer>
        <Btn @click="resetUser = null">{{ t('common.cancel') }}</Btn>
        <Btn variant="primary" type="submit" form="reset-form" :disabled="newPassword.length < 6">{{ t('users.reset') }}</Btn>
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
import { useI18n } from '../i18n/index.js'
import Btn from '../components/ui/Btn.vue'
import Badge from '../components/ui/Badge.vue'
import Icon from '../components/ui/Icon.vue'
import Modal from '../components/ui/Modal.vue'

const { t, locale } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()

const users = ref([])
const me = ref(null)
const showAdd = ref(false)
const form = reactive({ username: '', password: '', role: 'viewer' })
const error = ref('')
const resetUser = ref(null)
const newPassword = ref('')
const adminCount = computed(() => users.value.filter(u => u.role === 'admin').length)

function fmtDate(d) { return d ? new Date(d + 'Z').toLocaleString(locale.value, { dateStyle: 'medium', timeStyle: 'short' }) : '' }
function roleName(r) { return r === 'admin' ? t('users.roleAdmin') : t('users.roleViewer') }

async function load() {
  try {
    users.value = await api('/api/users')
    const info = await api('/api/auth/me')
    me.value = Number(info.sub)
  } catch (e) { toast.error(e.message) }
}

function openAdd() { Object.assign(form, { username: '', password: '', role: 'viewer' }); error.value = ''; showAdd.value = true }
async function addUser() {
  error.value = ''
  try {
    await api('/api/users', { method: 'POST', body: JSON.stringify(form) })
    showAdd.value = false
    toast.success(t('users.userCreated'))
    await load()
  } catch (e) { error.value = e.message }
}

async function changeRole(u, ev) {
  const role = ev.target.value
  if (!await confirm({ title: t('users.role'), message: t('users.roleConfirm', { user: u.username, role: roleName(role) }) })) { ev.target.value = u.role; return }
  try {
    await api(`/api/users/${u.id}`, { method: 'PUT', body: JSON.stringify({ role }) })
    toast.success(t('users.roleChanged', { user: u.username, role: roleName(role) }))
  } catch (e) { toast.error(e.message); ev.target.value = u.role }
  await load()
}

function openReset(u) { resetUser.value = u; newPassword.value = ''; error.value = '' }
async function doReset() {
  error.value = ''
  try {
    await api(`/api/users/${resetUser.value.id}`, { method: 'PUT', body: JSON.stringify({ password: newPassword.value }) })
    toast.success(t('users.pwReset', { user: resetUser.value.username }))
    resetUser.value = null
  } catch (e) { error.value = e.message }
}

async function deleteUser(u) {
  if (!await confirm({ title: t('users.delete'), message: t('users.deleteConfirm', { user: u.username }), danger: true, confirmText: t('users.delete') })) return
  try { await api(`/api/users/${u.id}`, { method: 'DELETE' }); toast.success(t('users.userDeleted')); await load() } catch (e) { toast.error(e.message) }
}

onMounted(load)
</script>
