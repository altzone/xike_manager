<template>
  <AuthShell :title="t('setup.title')" :subtitle="t('setup.subtitle')">
    <form @submit.prevent="doSetup" class="space-y-4" novalidate>
      <div>
        <label class="label" for="su-user">{{ t('login.username') }}</label>
        <input id="su-user" v-model.trim="username" type="text" required autofocus autocomplete="username" class="input" />
      </div>
      <div>
        <label class="label" for="su-pass">{{ t('login.password') }}</label>
        <input id="su-pass" v-model="password" type="password" required autocomplete="new-password" class="input" />
        <p class="hint mt-1">{{ t('setup.passwordHint') }}</p>
      </div>
      <div>
        <label class="label" for="su-pass2">{{ t('setup.confirmPassword') }}</label>
        <input id="su-pass2" v-model="password2" type="password" required autocomplete="new-password" class="input" />
      </div>
      <p v-if="error" class="text-sm text-danger-ink bg-danger-soft rounded-lg px-3 py-2" role="alert">{{ error }}</p>
      <Btn type="submit" variant="primary" size="lg" block :loading="loading" :disabled="!username || password.length < 6 || password !== password2">{{ t('setup.create') }}</Btn>
    </form>
  </AuthShell>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../composables/useApi.js'
import { useI18n } from '../i18n/index.js'
import AuthShell from '../components/AuthShell.vue'
import Btn from '../components/ui/Btn.vue'

const router = useRouter()
const { t } = useI18n()
const username = ref('')
const password = ref('')
const password2 = ref('')
const error = ref('')
const loading = ref(false)

async function doSetup() {
  if (password.value !== password2.value) { error.value = t('setup.passwordMismatch'); return }
  loading.value = true
  error.value = ''
  try {
    await api('/api/setup', { method: 'POST', body: JSON.stringify({ username: username.value, password: password.value }) })
    router.push('/login')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>
