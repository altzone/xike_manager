import { reactive, computed } from 'vue'
import en from './en.js'
import fr from './fr.js'
import zh from './zh.js'
import es from './es.js'
import pt from './pt.js'
import ar from './ar.js'
import de from './de.js'
import ru from './ru.js'
import ja from './ja.js'
import ko from './ko.js'
import tr from './tr.js'
import it from './it.js'

const messages = { en, fr, zh, es, pt, ar, de, ru, ja, ko, tr, it }

export const LANGUAGES = [
  { code: 'en', name: 'English', flag: '🇬🇧' },
  { code: 'fr', name: 'Français', flag: '🇫🇷' },
  { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
  { code: 'es', name: 'Español', flag: '🇪🇸' },
  { code: 'pt', name: 'Português', flag: '🇧🇷' },
  { code: 'it', name: 'Italiano', flag: '🇮🇹' },
  { code: 'tr', name: 'Türkçe', flag: '🇹🇷' },
  { code: 'ru', name: 'Русский', flag: '🇷🇺' },
  { code: 'ar', name: 'العربية', flag: '🇸🇦', rtl: true },
  { code: 'zh', name: '中文', flag: '🇨🇳' },
  { code: 'ja', name: '日本語', flag: '🇯🇵' },
  { code: 'ko', name: '한국어', flag: '🇰🇷' },
]

const state = reactive({
  locale: localStorage.getItem('locale') || 'en'
})

export function useI18n() {
  function t(key, params) {
    const lang = messages[state.locale] || messages.en
    let val = lang[key] || messages.en[key] || key
    if (params) {
      Object.entries(params).forEach(([k, v]) => { val = val.replace(`{${k}}`, v) })
    }
    return val
  }

  function setLocale(code) {
    state.locale = code
    localStorage.setItem('locale', code)
    document.documentElement.dir = LANGUAGES.find(l => l.code === code)?.rtl ? 'rtl' : 'ltr'
  }

  const locale = computed(() => state.locale)
  const isRtl = computed(() => LANGUAGES.find(l => l.code === state.locale)?.rtl || false)

  return { t, locale, setLocale, isRtl, LANGUAGES }
}
