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

function savedLocale() {
  try {
    const code = localStorage.getItem('locale')
    return messages[code] ? code : 'en'
  } catch (e) {
    return 'en'
  }
}

const state = reactive({ locale: savedLocale() })

function applyDocumentLocale(code) {
  document.documentElement.lang = code
  document.documentElement.dir = LANGUAGES.find(l => l.code === code)?.rtl ? 'rtl' : 'ltr'
}
// direction and language must also hold after a reload, not only after a click
applyDocumentLocale(state.locale)

export function useI18n() {
  function t(key, params) {
    const lang = messages[state.locale] || messages.en
    let val = lang[key] || messages.en[key] || key
    if (params) {
      // split/join: every occurrence, and no String.replace "$" pattern surprises in values
      Object.entries(params).forEach(([k, v]) => { val = val.split(`{${k}}`).join(String(v)) })
    }
    return val
  }

  function setLocale(code) {
    if (!messages[code]) return
    state.locale = code
    try { localStorage.setItem('locale', code) } catch (e) {}
    applyDocumentLocale(code)
  }

  const locale = computed(() => state.locale)
  const isRtl = computed(() => LANGUAGES.find(l => l.code === state.locale)?.rtl || false)

  return { t, locale, setLocale, isRtl, LANGUAGES }
}
