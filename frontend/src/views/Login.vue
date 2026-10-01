<template>
  <AuthShell :title="t('login.title')" :subtitle="t('login.subtitle')">
    <form @submit.prevent="doLogin" class="space-y-4" novalidate>
      <div>
        <label class="label" for="username">{{ t('login.username') }}</label>
        <input id="username" v-model.trim="username" type="text" required autofocus autocomplete="username" class="input" />
      </div>
      <div>
        <label class="label" for="password">{{ t('login.password') }}</label>
        <input id="password" v-model="password" type="password" required autocomplete="current-password" class="input" />
      </div>
      <p v-if="error" class="text-sm text-danger-ink bg-danger-soft rounded-lg px-3 py-2 flex items-center gap-2" role="alert">
        <Icon name="x-circle" :size="16" class="shrink-0" />{{ error }}
      </p>
      <Btn type="submit" variant="primary" size="lg" block :loading="loading" :disabled="!username || !password">{{ t('login.signin') }}</Btn>
    </form>
  </AuthShell>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useI18n } from '../i18n/index.js'
import AuthShell from '../components/AuthShell.vue'
import Btn from '../components/ui/Btn.vue'
import Icon from '../components/ui/Icon.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { t } = useI18n()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

onMounted(async () => {
  try {
    const res = await fetch('/api/setup/status')
    const data = await res.json()
    if (!data.setup_complete) router.replace('/setup')
  } catch (e) {}
})

async function doLogin() {
  loading.value = true
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    const back = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/'
    router.push(back)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>
