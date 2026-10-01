import { reactive } from 'vue'

// One app-wide confirm dialog (rendered by ConfirmDialog.vue in the shell),
// used as `if (await confirm({ title, message, danger: true })) …`
const state = reactive({ open: false, title: '', message: '', confirmText: '', cancelText: '', danger: false, resolve: null })

export function useConfirm() {
  function confirm(opts) {
    return new Promise((resolve) => {
      if (state.resolve) state.resolve(false)
      Object.assign(state, {
        open: true,
        title: opts.title || '',
        message: opts.message || '',
        confirmText: opts.confirmText || '',
        cancelText: opts.cancelText || '',
        danger: !!opts.danger,
        resolve,
      })
    })
  }
  function settle(value) {
    const r = state.resolve
    state.open = false
    state.resolve = null
    if (r) r(value)
  }
  return { state, confirm, settle }
}
