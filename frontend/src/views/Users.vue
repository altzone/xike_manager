<template>
  <div class="max-w-4xl mx-auto p-6">
    <div class="flex items-center justify-between mb-8">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{{ t('users.title') }}</h1>
        <p class="text-sm text-gray-400 mt-1">{{ t('users.subtitle') }}</p>
      </div>
      <div class="flex gap-2">
        <router-link to="/" class="px-4 py-2 bg-gray-100 text-gray-600 text-sm rounded-lg hover:bg-gray-200 transition">{{ t('users.back') }}</router-link>
        <button @click="showAdd = true" class="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition flex items-center gap-1.5">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
          {{ t('users.addUser') }}
        </button>
      </div>
    </div>

    <!-- Users list -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-50/80">
          <tr>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">{{ t('users.username') }}</th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">{{ t('users.role') }}</th>
            <th class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider">{{ t('users.created') }}</th>
            <th class="px-5 py-3 text-right font-medium text-gray-500 text-xs uppercase tracking-wider">{{ t('users.actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-50">
          <tr v-for="u in users" :key="u.id" class="hover:bg-gray-50/50 transition">
            <td class="px-5 py-3">
              <div class="flex items-center gap-2">
                <div class="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
                  :class="u.role === 'admin' ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-500'">
                  {{ u.username[0]?.toUpperCase() }}
                </div>
                <span class="font-medium text-gray-900">{{ u.username }}</span>
              </div>
            </td>
            <td class="px-5 py-3">
              <select v-model="u.role" @change="updateRole(u)" class="text-xs px-2 py-1 rounded-lg border transition"
                :class="u.role === 'admin' ? 'bg-indigo-50 border-indigo-200 text-indigo-700' : 'bg-gray-50 border-gray-200 text-gray-600'">
                <option value="admin">{{ t('users.admin') }}</option>
                <option value="viewer">{{ t('users.viewer') }}</option>
              </select>
            </td>
            <td class="px-5 py-3 text-gray-500">{{ formatDate(u.created_at) }}</td>
            <td class="px-5 py-3 text-right">
              <div class="flex gap-1.5 justify-end">
                <button @click="resetPw(u)" class="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200 transition">{{ t('users.resetPw') }}</button>
                <button @click="deleteUser(u)" class="px-2 py-1 text-xs bg-red-50 text-red-600 rounded hover:bg-red-100 transition" :disabled="u.username === currentUser">{{ t('users.delete') }}</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Roles info -->
    <div class="mt-6 bg-gray-50 rounded-xl p-5 text-sm text-gray-500">
      <h3 class="font-semibold text-gray-700 mb-2">{{ t('users.rolePerms') }}</h3>
      <div class="grid grid-cols-2 gap-4">
        <div>
          <p class="font-medium text-gray-700">{{ t('users.roleAdmin') }}</p>
          <p class="text-xs text-gray-400">{{ t('users.roleAdminDesc') }}</p>
        </div>
        <div>
          <p class="font-medium text-gray-700">{{ t('users.roleViewer') }}</p>
          <p class="text-xs text-gray-400">{{ t('users.roleViewerDesc') }}</p>
        </div>
      </div>
    </div>

    <!-- Add modal -->
    <div v-if="showAdd" class="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50" @click.self="showAdd = false">
      <div class="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl">
        <h2 class="text-lg font-bold mb-4">{{ t('users.addUser') }}</h2>
        <form @submit.prevent="addUser" class="space-y-3">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('users.username') }}</label>
            <input v-model="form.username" required class="w-full px-3 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"/>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('login.password') }}</label>
            <input v-model="form.password" type="password" required class="w-full px-3 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"/>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ t('users.role') }}</label>
            <select v-model="form.role" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none">
              <option value="admin">{{ t('users.roleAdmin') }}</option>
              <option value="viewer">{{ t('users.roleViewer') }}</option>
            </select>
          </div>
          <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>
          <div class="flex gap-3 pt-1">
            <button type="button" @click="showAdd = false" class="flex-1 py-2.5 border rounded-lg text-gray-600 hover:bg-gray-50">{{ t('common.cancel') }}</button>
            <button type="submit" class="flex-1 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">{{ t('vlans.create') }}</button>
          </div>
        </form>
      </div>
    </div>

    <!-- Reset password modal -->
    <div v-if="resetUser" class="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50" @click.self="resetUser = null">
      <div class="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl">
        <h2 class="text-lg font-bold mb-4">{{ t('users.resetPw') }}: {{ resetUser.username }}</h2>
        <form @submit.prevent="doResetPw" class="space-y-3">
          <input v-model="newPassword" type="password" required :placeholder="t('users.newPw')" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"/>
          <div class="flex gap-3">
            <button type="button" @click="resetUser = null" class="flex-1 py-2.5 border rounded-lg text-gray-600 hover:bg-gray-50">{{ t('common.cancel') }}</button>
            <button type="submit" class="flex-1 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">{{ t('users.reset') }}</button>
          </div>
        </form>
      </div>
    </div>

    <p v-if="msg" class="mt-4 text-sm" :class="msgOk ? 'text-emerald-600' : 'text-red-500'">{{ msg }}</p>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { api } from '../composables/useApi.js'
import { useI18n } from '../i18n/index.js'

const { t } = useI18n()

const users = ref([])
const showAdd = ref(false)
const form = reactive({ username: '', password: '', role: 'viewer' })
const error = ref('')
const resetUser = ref(null)
const newPassword = ref('')
const msg = ref('')
const msgOk = ref(true)
const currentUser = localStorage.getItem('username')

function flash(m, ok = true) { msg.value = m; msgOk.value = ok; setTimeout(() => msg.value = '', 3000) }
function formatDate(d) { return d ? new Date(d + 'Z').toLocaleString() : '' }

async function load() { users.value = await api('/api/users') }

async function addUser() {
  error.value = ''
  try {
    await api('/api/users', { method: 'POST', body: JSON.stringify(form) })
    showAdd.value = false; form.username = ''; form.password = ''; form.role = 'viewer'
    flash(t('users.userCreated')); await load()
  } catch (e) { error.value = e.message }
}

async function updateRole(u) {
  await api(`/api/users/${u.id}`, { method: 'PUT', body: JSON.stringify({ role: u.role }) })
  flash(t('users.roleChanged', { user: u.username, role: u.role }))
}

function resetPw(u) { resetUser.value = u; newPassword.value = '' }
async function doResetPw() {
  await api(`/api/users/${resetUser.value.id}`, { method: 'PUT', body: JSON.stringify({ password: newPassword.value }) })
  flash(t('users.pwReset', { user: resetUser.value.username })); resetUser.value = null
}

async function deleteUser(u) {
  if (u.username === currentUser) return
  if (!confirm(t('users.deleteConfirm', { user: u.username }))) return
  await api(`/api/users/${u.id}`, { method: 'DELETE' })
  flash(t('users.userDeleted')); await load()
}

onMounted(load)
</script>
