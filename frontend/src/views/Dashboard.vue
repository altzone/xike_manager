<template>
  <div class="max-w-6xl mx-auto p-6">
    <div class="flex items-center justify-between mb-8">
      <h1 class="text-2xl font-bold text-gray-900">Switches</h1>
      <button @click="showAdd = true"
        class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition flex items-center gap-2">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
        Add Switch
      </button>
    </div>

    <!-- Switch cards -->
    <div v-if="switches.length" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <router-link v-for="sw in switches" :key="sw.id" :to="`/switch/${sw.id}`"
        class="bg-white rounded-xl border border-gray-200 p-6 hover:shadow-lg hover:border-indigo-300 transition group">
        <div class="flex items-start justify-between">
          <div>
            <h3 class="font-semibold text-gray-900 group-hover:text-indigo-600 transition">{{ sw.name }}</h3>
            <p class="text-sm text-gray-500 mt-1">{{ sw.ip }}</p>
          </div>
          <div class="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center">
            <svg class="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01"/>
            </svg>
          </div>
        </div>
        <div class="mt-4 flex gap-3 text-xs text-gray-400">
          <span>{{ sw.model }}</span>
          <span>FW {{ sw.firmware }}</span>
        </div>
      </router-link>
    </div>

    <div v-else class="text-center py-20">
      <div class="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
        <svg class="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
        </svg>
      </div>
      <p class="text-gray-500">No switches configured</p>
      <button @click="showAdd = true" class="mt-3 text-indigo-600 text-sm font-medium hover:underline">Add your first switch</button>
    </div>

    <!-- Add modal -->
    <div v-if="showAdd" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="showAdd = false">
      <div class="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl">
        <h2 class="text-lg font-bold mb-4">Add Switch</h2>
        <form @submit.prevent="doAdd" class="space-y-3">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input v-model="form.name" required placeholder="e.g. SW-Bureau"
              class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"/>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">IP Address</label>
            <input v-model="form.ip" required placeholder="10.1.10.40"
              class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"/>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Username</label>
              <input v-model="form.username" required
                class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"/>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
              <input v-model="form.password" type="password" required
                class="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"/>
            </div>
          </div>
          <p v-if="addError" class="text-red-500 text-sm">{{ addError }}</p>
          <div class="flex gap-3 pt-2">
            <button type="button" @click="showAdd = false" class="flex-1 py-2 border rounded-lg text-gray-600 hover:bg-gray-50">Cancel</button>
            <button type="submit" :disabled="adding" class="flex-1 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
              {{ adding ? 'Testing...' : 'Add' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../composables/useApi.js'

const switches = ref([])
const showAdd = ref(false)
const adding = ref(false)
const addError = ref('')
const form = ref({ name: '', ip: '', username: 'admin', password: 'admin' })

async function load() {
  switches.value = await api('/api/switches')
}

async function doAdd() {
  adding.value = true
  addError.value = ''
  try {
    await api('/api/switches', { method: 'POST', body: JSON.stringify(form.value) })
    showAdd.value = false
    form.value = { name: '', ip: '', username: 'admin', password: 'admin' }
    await load()
  } catch (e) {
    addError.value = e.message
  } finally {
    adding.value = false
  }
}

onMounted(load)
</script>
