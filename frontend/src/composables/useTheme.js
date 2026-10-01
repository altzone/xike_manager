import { ref, watch } from 'vue'

const stored = (() => { try { return localStorage.getItem('theme') } catch (e) { return null } })()
const theme = ref(['light', 'dark', 'system'].includes(stored) ? stored : 'system')
const media = window.matchMedia('(prefers-color-scheme: dark)')

function apply() {
  const dark = theme.value === 'dark' || (theme.value === 'system' && media.matches)
  document.documentElement.classList.toggle('dark', dark)
}
apply()
media.addEventListener('change', apply)
watch(theme, (v) => { try { localStorage.setItem('theme', v) } catch (e) {} ; apply() })

export function useTheme() {
  function cycle() { theme.value = { light: 'dark', dark: 'system', system: 'light' }[theme.value] }
  return { theme, cycle }
}
