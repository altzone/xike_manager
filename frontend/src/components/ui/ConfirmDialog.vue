<template>
  <Modal :open="state.open" :title="state.title || t('common.confirm')" width="sm" @close="settle(false)">
    <div class="flex gap-3">
      <div class="w-9 h-9 rounded-full flex items-center justify-center shrink-0" :class="state.danger ? 'bg-danger-soft text-danger' : 'bg-accent-soft text-accent'">
        <Icon :name="state.danger ? 'warning' : 'question'" :size="18" />
      </div>
      <p class="text-sm text-ink-2 leading-relaxed pt-1.5 whitespace-pre-line">{{ state.message }}</p>
    </div>
    <template #footer>
      <Btn @click="settle(false)">{{ state.cancelText || t('common.cancel') }}</Btn>
      <Btn :variant="state.danger ? 'danger' : 'primary'" autofocus @click="settle(true)">{{ state.confirmText || t('common.confirm') }}</Btn>
    </template>
  </Modal>
</template>

<script setup>
import Modal from './Modal.vue'
import Btn from './Btn.vue'
import Icon from './Icon.vue'
import { useConfirm } from '../../composables/useConfirm.js'
import { useI18n } from '../../i18n/index.js'

const { state, settle } = useConfirm()
const { t } = useI18n()
</script>
