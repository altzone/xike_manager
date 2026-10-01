<template>
  <div class="min-h-screen flex bg-bg text-ink">
    <!-- Sidebar (desktop) -->
    <aside class="hidden lg:flex flex-col w-60 shrink-0 bg-side text-side-ink sticky top-0 h-screen border-e border-side-line">
      <SidebarContent @navigate="drawer = false" />
    </aside>

    <!-- Sidebar (mobile drawer) -->
    <Teleport to="body">
      <transition name="fade">
        <div v-if="drawer" class="fixed inset-0 z-[80] bg-black/50 lg:hidden" @click="drawer = false"></div>
      </transition>
      <transition name="drawer">
        <aside v-if="drawer" class="fixed inset-y-0 start-0 z-[81] w-64 flex flex-col bg-side text-side-ink lg:hidden shadow-[var(--shadow-pop)]">
          <SidebarContent @navigate="drawer = false" />
        </aside>
      </transition>
    </Teleport>

    <div class="flex-1 min-w-0 flex flex-col">
      <!-- Top bar -->
      <header class="h-14 bg-surface border-b border-line flex items-center gap-3 px-4 lg:px-6 sticky top-0 z-40">
        <Btn class="lg:hidden" variant="ghost" icon="menu" icon-only :aria-label="t('ui.menu')" @click="drawer = true" />
        <div class="min-w-0 flex-1">
          <p v-if="sw.current" class="text-[11px] text-muted truncate leading-none mb-0.5">{{ sw.current.name }} · <span class="mono">{{ sw.current.ip }}</span></p>
          <h1 class="text-[15px] font-semibold truncate leading-tight">{{ pageTitle }}</h1>
        </div>
        <div v-if="sw.current && sw.status.checked" class="hidden sm:flex items-center gap-2">
          <Badge :tone="sw.status.online ? 'ok' : 'danger'" dot>{{ sw.status.online ? t('sw.online') : t('sw.offline') }}</Badge>
          <Badge v-if="sw.status.online && sw.status.temperature" :tone="Number(sw.status.temperature) > 60 ? 'warn' : 'neutral'">{{ sw.status.temperature }}°C</Badge>
        </div>

        <!-- Theme -->
        <Btn variant="ghost" :icon="themeIcon" icon-only :aria-label="t('ui.theme')" :title="t('ui.theme') + ': ' + t('ui.theme_' + theme)" @click="cycle" />

        <!-- Language -->
        <div class="relative" ref="langRef">
          <Btn variant="ghost" size="md" :aria-label="t('ui.language')" @click="showLang = !showLang">
            <span class="text-base leading-none">{{ currentLang?.flag }}</span>
            <span class="hidden md:inline text-xs">{{ currentLang?.name }}</span>
            <Icon name="chevron-down" :size="14" />
          </Btn>
          <transition name="pop">
            <div v-if="showLang" class="absolute end-0 top-full mt-1 w-48 card py-1 max-h-80 overflow-auto z-50 shadow-[var(--shadow-pop)]">
              <button v-for="lang in i18n.LANGUAGES" :key="lang.code" @click="i18n.setLocale(lang.code); showLang = false"
                class="w-full px-3 py-2 text-start text-sm flex items-center gap-2.5 hover:bg-surface-2 transition"
                :class="lang.code === i18n.locale.value ? 'text-accent font-medium' : 'text-ink-2'">
                <span class="text-base leading-none">{{ lang.flag }}</span>
                <span class="flex-1">{{ lang.name }}</span>
                <Icon v-if="lang.code === i18n.locale.value" name="check" :size="14" />
              </button>
            </div>
          </transition>
        </div>
      </header>

      <main class="flex-1 p-4 sm:p-6 lg:p-8">
        <div class="max-w-[1320px] mx-auto w-full">
          <router-view />
        </div>
      </main>
    </div>

    <!-- Toasts -->
    <Teleport to="body">
      <div class="fixed bottom-4 end-4 z-[100] flex flex-col gap-2 w-[min(92vw,360px)] pointer-events-none">
        <transition-group name="toast">
          <div v-for="tst in toast.toasts" :key="tst.id" role="status"
            class="pointer-events-auto flex items-start gap-3 px-4 py-3 rounded-xl border shadow-[var(--shadow-pop)] bg-surface text-sm"
            :class="tst.ok ? 'border-ok/40' : 'border-danger/40'">
            <Icon :name="tst.ok ? 'check-circle' : 'x-circle'" :size="18" class="mt-0.5 shrink-0" :class="tst.ok ? 'text-ok' : 'text-danger'" />
            <span class="flex-1 text-ink leading-snug break-words">{{ tst.msg }}</span>
            <button class="text-faint hover:text-ink" :aria-label="t('common.close')" @click="toast.dismiss(tst.id)"><Icon name="x" :size="14" /></button>
          </div>
        </transition-group>
      </div>
    </Teleport>

    <ConfirmDialog />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, defineComponent, h } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useSwitchesStore } from '../stores/switches.js'
import { useToast } from '../composables/useToast.js'
import { useTheme } from '../composables/useTheme.js'
import { useI18n } from '../i18n/index.js'
import Btn from '../components/ui/Btn.vue'
import Badge from '../components/ui/Badge.vue'
import Icon from '../components/ui/Icon.vue'
import ConfirmDialog from '../components/ui/ConfirmDialog.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const sw = useSwitchesStore()
const toast = useToast()
const i18n = useI18n()
const { t } = i18n
const { theme, cycle } = useTheme()

const drawer = ref(false)
const showLang = ref(false)
const langRef = ref(null)
const currentLang = computed(() => i18n.LANGUAGES.find(l => l.code === i18n.locale.value))
const themeIcon = computed(() => ({ light: 'sun', dark: 'moon', system: 'monitor' }[theme.value]))
const pageTitle = computed(() => route.meta.title ? t(route.meta.title) : 'SwitchPilot')

function onDocClick(e) { if (langRef.value && !langRef.value.contains(e.target)) showLang.value = false }
onMounted(() => { document.addEventListener('click', onDocClick); auth.refresh(); sw.load().catch(() => {}) })
onUnmounted(() => document.removeEventListener('click', onDocClick))
watch(() => route.fullPath, () => { drawer.value = false })

// ── Sidebar (shared between desktop and the mobile drawer) ──
const NAV = [
  { name: 'switch-dashboard', icon: 'overview', label: 'nav.overview', path: '' },
  { name: 'switch-ports', icon: 'ports', label: 'nav.ports', path: '/ports' },
  { name: 'switch-vlans', icon: 'vlans', label: 'nav.vlans', path: '/vlans' },
  { name: 'switch-lag', icon: 'lag', label: 'nav.lag', path: '/lag' },
  { name: 'switch-monitoring', icon: 'mac', label: 'nav.mac', path: '/monitoring' },
  { name: 'switch-system', icon: 'system', label: 'nav.system', path: '/system' },
]

const SidebarContent = defineComponent({
  emits: ['navigate'],
  setup(_, { emit }) {
    const picker = ref(false)
    const pickerRef = ref(null)
    function onDoc(e) { if (pickerRef.value && !pickerRef.value.contains(e.target)) picker.value = false }
    onMounted(() => document.addEventListener('click', onDoc))
    onUnmounted(() => document.removeEventListener('click', onDoc))
    function go(to) { picker.value = false; emit('navigate'); router.push(to) }
    function doLogout() { auth.logout(); router.push('/login') }

    const linkBase = 'flex items-center gap-3 px-3 py-2 rounded-lg text-[13.5px] font-medium transition-colors'
    const linkIdle = 'text-side-muted hover:text-side-ink hover:bg-side-2'
    const linkActive = 'bg-side-2 text-white shadow-inner'

    return () => h('div', { class: 'flex flex-col h-full' }, [
      // brand
      h('div', { class: 'h-14 flex items-center gap-2.5 px-4 border-b border-side-line' }, [
        h('img', { src: '/switch.svg', alt: '', class: 'w-7 h-7' }),
        h('span', { class: 'font-semibold tracking-tight text-[15px] text-white' }, 'SwitchPilot'),
      ]),
      // switch picker
      h('div', { class: 'px-3 pt-3', ref: pickerRef }, [
        h('div', { class: 'relative' }, [
          h('button', {
            class: 'w-full flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-start bg-side-2 hover:bg-side-line/60 transition border border-side-line',
            onClick: () => picker.value = !picker.value, 'aria-haspopup': 'listbox', 'aria-expanded': picker.value,
          }, [
            h('span', { class: 'dot ' + (sw.current ? (sw.status.online === false ? 'bg-danger' : sw.status.online ? 'bg-ok live-dot' : 'bg-faint') : 'bg-faint') }),
            h('span', { class: 'min-w-0 flex-1' }, [
              h('span', { class: 'block text-[13px] font-medium text-white truncate' }, sw.current ? sw.current.name : t('ui.pickSwitch')),
              h('span', { class: 'block text-[11px] text-side-muted truncate mono' }, sw.current ? sw.current.ip : t('ui.switchCount', { n: sw.list.length })),
            ]),
            h(Icon, { name: 'chevron-updown', size: 14, class: 'text-side-muted' }),
          ]),
          picker.value ? h('div', { class: 'absolute inset-x-0 top-full mt-1 z-50 rounded-lg bg-side-2 border border-side-line shadow-[var(--shadow-pop)] py-1 max-h-72 overflow-auto', role: 'listbox' }, [
            ...sw.list.map(s => h('button', {
              class: 'w-full flex items-center gap-2.5 px-3 py-2 text-start hover:bg-side-line/60 transition ' + (sw.currentId === s.id ? 'text-white' : 'text-side-ink'),
              role: 'option', 'aria-selected': sw.currentId === s.id, onClick: () => go(`/switch/${s.id}`),
            }, [
              h(Icon, { name: 'switch', size: 15, class: 'text-side-muted' }),
              h('span', { class: 'min-w-0 flex-1' }, [
                h('span', { class: 'block text-[13px] truncate' }, s.name),
                h('span', { class: 'block text-[11px] text-side-muted mono truncate' }, s.ip),
              ]),
              sw.currentId === s.id ? h(Icon, { name: 'check', size: 14 }) : null,
            ])),
            sw.list.length ? h('div', { class: 'my-1 border-t border-side-line' }) : null,
            h('button', { class: 'w-full flex items-center gap-2.5 px-3 py-2 text-start text-[13px] text-side-muted hover:text-white hover:bg-side-line/60 transition', onClick: () => go('/') },
              [h(Icon, { name: 'plus', size: 15 }), t('dash.addSwitch')]),
          ]) : null,
        ]),
      ]),
      // per-switch nav
      h('nav', { class: 'px-3 pt-4 space-y-0.5 flex-1', 'aria-label': 'Switch' }, [
        sw.current ? h('p', { class: 'eyebrow text-side-muted px-3 pb-1.5' }, t('sw.managing')) : null,
        ...(sw.current ? NAV.map(item => h(RouterLink, { to: `/switch/${sw.currentId}${item.path}`, custom: true }, {
          default: ({ navigate }) => h('a', {
            href: `/switch/${sw.currentId}${item.path}`,
            class: [linkBase, route.name === item.name ? linkActive : linkIdle],
            'aria-current': route.name === item.name ? 'page' : undefined,
            onClick: (e) => { e.preventDefault(); emit('navigate'); navigate(e) },
          }, [h(Icon, { name: item.icon, size: 17 }), t(item.label)]),
        })) : []),
        h('div', { class: 'pt-4 pb-1.5' }, [h('p', { class: 'eyebrow text-side-muted px-3' }, t('ui.general'))]),
        h('a', { href: '/', class: [linkBase, route.name === 'dashboard' ? linkActive : linkIdle], onClick: (e) => { e.preventDefault(); go('/') } },
          [h(Icon, { name: 'switch', size: 17 }), t('nav.allSwitches')]),
        auth.isAdmin ? h('a', { href: '/users', class: [linkBase, route.name === 'users' ? linkActive : linkIdle], onClick: (e) => { e.preventDefault(); go('/users') } },
          [h(Icon, { name: 'users', size: 17 }), t('nav.users')]) : null,
      ]),
      // user
      h('div', { class: 'p-3 border-t border-side-line flex items-center gap-2.5' }, [
        h('div', { class: 'w-8 h-8 rounded-full bg-accent text-white flex items-center justify-center text-xs font-semibold shrink-0' }, (auth.username || '?')[0].toUpperCase()),
        h('div', { class: 'min-w-0 flex-1' }, [
          h('p', { class: 'text-[13px] font-medium text-white truncate' }, auth.username),
          h('p', { class: 'text-[11px] text-side-muted' }, auth.isAdmin ? t('users.roleAdmin') : t('users.roleViewer')),
        ]),
        h(Btn, { variant: 'ghost', icon: 'logout', iconOnly: true, size: 'sm', ariaLabel: t('nav.logout'), title: t('nav.logout'), class: 'text-side-muted hover:text-white hover:bg-side-2', onClick: doLogout }),
      ]),
    ])
  },
})
</script>

<style>
.drawer-enter-active, .drawer-leave-active { transition: transform .22s cubic-bezier(.2,.8,.2,1); }
.drawer-enter-from, .drawer-leave-to { transform: translateX(-100%); }
[dir="rtl"] .drawer-enter-from, [dir="rtl"] .drawer-leave-to { transform: translateX(100%); }
</style>
