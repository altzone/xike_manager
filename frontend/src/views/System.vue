<template>
  <div class="space-y-5">
    <p class="hint max-w-3xl">{{ t('sys.tip') }}</p>

    <!-- Device + network -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <Section :title="t('sys.device')" icon="chip" :state="st.status">
        <dl class="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
          <dt class="text-muted">{{ t('swdash.model') }}</dt><dd class="text-ink text-end">{{ info.modle || '—' }}</dd>
          <dt class="text-muted">{{ t('dash.firmware') }}</dt><dd class="text-ink text-end mono">{{ info.fw_ver || '—' }}</dd>
          <dt class="text-muted">{{ t('sys.hardware') }}</dt><dd class="text-ink text-end mono">{{ info.hw_ver || '—' }}</dd>
          <dt class="text-muted">{{ t('sys.macAddress') }}</dt><dd class="text-ink text-end mono">{{ info.sys_macaddr || '—' }}</dd>
          <dt class="text-muted">{{ t('swdash.temperature') }}</dt><dd class="text-ink text-end num"><bdi v-if="info.temperature" dir="ltr">{{ info.temperature }} °C</bdi><template v-else>—</template></dd>
        </dl>
        <div class="divider my-4"></div>
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-sm font-medium text-ink inline-flex items-center gap-1.5">{{ t('sys.portMap') }} <Tip :title="t('sys.portMap')" :text="t('sys.portMapTip')" /></p>
            <p class="hint mt-0.5">{{ t('sys.portMapDesc') }}</p>
            <p class="text-sm text-ink-2 mt-1.5">{{ t('sys.portMapCurrent', { a: swapSfp ? 10 : 9, b: swapSfp ? 9 : 10 }) }}</p>
            <p v-if="portMapMismatch" role="status" class="text-sm text-warn-ink bg-warn-soft rounded-lg px-3 py-2 mt-2 flex items-start gap-2">
              <Icon name="warning" :size="15" class="mt-0.5 shrink-0" /><span>{{ t('sys.portMapCheck', { fw: info.fw_ver }) }}</span>
            </p>
            <label class="flex items-center gap-2 hint mt-2 cursor-pointer"><input type="checkbox" v-model="moveDescriptions" class="accent-accent"> {{ t('sys.portMapMoveDesc') }}</label>
          </div>
          <div class="flex flex-col items-end gap-1 shrink-0">
            <Toggle :model-value="swapSfp" :disabled="!auth.isAdmin" :label="t('sys.portMapToggle')" @update:model-value="togglePortMap" />
            <span class="text-[11px] text-muted text-end max-w-[140px]">{{ t('sys.portMapToggle') }}</span>
          </div>
        </div>
      </Section>

      <Section :title="t('sys.mgmtIface')" icon="network" :state="st.status" :tip="t('sys.mgmtTip')" :locked="locked('network')">
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-sm text-ink-2">{{ t('sys.dhcp') }}</span>
            <Toggle v-model="net.dhcp" :disabled="!can('network')" :label="t('sys.dhcp')" />
          </div>
          <template v-if="!net.dhcp">
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div><label class="label" for="sys-net-ip">{{ t('sys.ipAddress') }}</label><input id="sys-net-ip" v-model.trim="net.ip" class="input input-sm mono" :disabled="!can('network')" /></div>
              <div><label class="label" for="sys-net-mask">{{ t('sys.netmask') }}</label><input id="sys-net-mask" v-model.trim="net.netmask" class="input input-sm mono" :disabled="!can('network')" /></div>
              <div><label class="label" for="sys-net-gw">{{ t('sys.gateway') }}</label><input id="sys-net-gw" v-model.trim="net.gateway" class="input input-sm mono" :disabled="!can('network')" /></div>
            </div>
          </template>
          <p v-else class="hint">{{ t('sys.dhcpAuto') }}</p>
          <div class="flex items-center justify-between gap-3">
            <p class="text-[11px] text-danger-ink flex items-center gap-1"><Icon name="warning" :size="13" />{{ t('sys.ipWarning') }}</p>
            <Btn v-if="can('network')" size="sm" variant="primary" :loading="busy.net" @click="applyNetwork">{{ net.dhcp ? t('sys.applyDhcp') : t('sys.applyStatic') }}</Btn>
          </div>
        </div>
      </Section>
    </div>

    <!-- Clock -->
    <Section :title="t('sys.clock')" icon="clock" :state="st.time" :tip="t('sys.clockTip')" :unsupported="st.time === 'unsupported'" :locked="locked('time')">
      <template #actions>
        <span class="num text-sm text-ink bg-surface-2 border border-line rounded-lg px-2.5 py-1">{{ timeData.timeVal || '--:--:--' }}</span>
        <span class="num text-sm text-ink bg-surface-2 border border-line rounded-lg px-2.5 py-1">{{ timeData.dateVal || '--/--/----' }}</span>
        <Badge tone="neutral">UTC {{ timeData.timezoneOffsetVal || '' }}</Badge>
      </template>
      <div class="flex flex-wrap gap-2 mb-4">
        <button v-for="m in ['sntp', 'manual']" :key="m" type="button" :aria-pressed="timeMode === m" @click="timeMode = m" class="px-3.5 py-1.5 rounded-lg text-sm font-medium border transition" :class="timeMode === m ? 'border-accent bg-accent-soft text-accent-ink' : 'border-line text-muted hover:border-line-strong'">{{ m === 'sntp' ? t('sys.sntpAuto') : t('sys.manual') }}</button>
      </div>
      <div v-if="timeMode === 'sntp'" class="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
        <div><label class="label" for="sys-ntp-server">{{ t('sys.ntpServer') }}</label><input id="sys-ntp-server" v-model.trim="sntp.server" class="input input-sm mono" placeholder="pool.ntp.org" :disabled="!can('time')" /></div>
        <div><label class="label" for="sys-ntp-poll">{{ t('sys.pollInterval') }}</label><input id="sys-ntp-poll" v-model.number="sntp.poll" type="number" min="16" max="99999" class="input input-sm num" :disabled="!can('time')" /></div>
        <div><label class="label" for="sys-tz-sntp">{{ t('sys.timezone') }}</label><select id="sys-tz-sntp" v-model="tz.timezone" class="select select-sm" :disabled="!can('time')"><option v-for="o in tzOptions" :key="o" :value="o">UTC {{ o }}</option></select></div>
        <div class="flex gap-2">
          <Btn v-if="can('time')" size="sm" variant="primary" class="flex-1" :loading="busy.sntp" @click="applySntp(true)">{{ sntp.enabled ? t('sys.updateSntp') : t('sys.enableSntp') }}</Btn>
          <Btn size="sm" @click="checkSntp">{{ t('sys.check') }}</Btn>
        </div>
        <div v-if="sntpStatus" class="md:col-span-4 text-xs flex items-center gap-2 px-3 py-2 rounded-lg" :class="sntpStatus.synced ? 'bg-ok-soft text-ok-ink' : 'bg-warn-soft text-warn-ink'">
          <span class="dot" :class="sntpStatus.synced ? 'bg-ok' : 'bg-warn'"></span>
          <span>{{ sntpStatus.synced ? t('sys.sntpSynced') : t('sys.sntpNotSynced') }} · {{ sntpStatus.server_ip || '—' }} · {{ sntpStatus.time }} {{ sntpStatus.date }}</span>
        </div>
        <p v-if="sntpResolved" class="md:col-span-4 hint">{{ t('sys.resolved') }} <span class="mono text-ink">{{ sntpResolved }}</span></p>
      </div>
      <div v-else class="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
        <div><label class="label" for="sys-time">{{ t('sys.time') }}</label><input id="sys-time" v-model.trim="tz.time" class="input input-sm mono" placeholder="14:30:00" :disabled="!can('time')" /></div>
        <div><label class="label" for="sys-date">{{ t('sys.date') }}</label><input id="sys-date" v-model.trim="tz.date" class="input input-sm mono" placeholder="01/10/2026" :disabled="!can('time')" /></div>
        <div><label class="label" for="sys-tz-manual">{{ t('sys.timezone') }}</label><select id="sys-tz-manual" v-model="tz.timezone" class="select select-sm" :disabled="!can('time')"><option v-for="o in tzOptions" :key="o" :value="o">UTC {{ o }}</option></select></div>
        <Btn v-if="can('time')" size="sm" variant="primary" :loading="busy.time" @click="applyTime">{{ t('sys.setTime') }}</Btn>
        <label class="md:col-span-4 flex items-center gap-2 text-sm text-ink-2 cursor-pointer"><input type="checkbox" v-model="tz.daylight" class="accent-accent" :disabled="!can('time')"> {{ t('sys.timezoneDst') }}</label>
      </div>
    </Section>

    <!-- Features -->
    <div class="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-4 gap-5">
      <Section :title="t('sys.stp')" icon="shield" :state="st.stp" :tip="t('sys.stpTip')" compact :locked="locked('stp')">
        <template #actions><Toggle v-model="stp.enabled" :disabled="!can('stp')" :label="t('sys.stp')" @update:model-value="applyStp" /></template>
        <select v-if="stp.enabled" v-model="stp.mode" @change="applyStp" :disabled="!can('stp')" :aria-label="t('sys.stp')" class="select select-sm"><option value="stp">{{ t('sys.stpClassic') }}</option><option value="rstp">{{ t('sys.stpRapid') }}</option></select>
        <p v-else class="hint">{{ t('common.off') }}</p>
      </Section>
      <Section :title="t('sys.storm')" icon="bolt" :state="st.storm" :tip="storm.v2 ? t('sys.stormTipV2') : t('sys.stormTip')" compact :locked="locked('storm')">
        <template #actions><Toggle v-model="storm.enabled" :disabled="!can('storm') || busy.storm" :label="t('sys.storm')" @update:model-value="applyStorm" /></template>
        <div v-if="storm.enabled" class="space-y-2.5">
          <div><label class="label" for="sys-storm-rate">{{ storm.v2 ? t('sys.stormRateMbps') : t('sys.stormRate') }}</label><input id="sys-storm-rate" v-model.number="storm.rate" type="number" min="1" max="1000" @change="applyStorm" :disabled="!can('storm') || busy.storm" class="input input-sm num" /></div>
          <!-- 2.0.0.x: a limit per traffic type (SwitchPilot sets the same one on every port) -->
          <div v-if="storm.v2" class="space-y-1.5" role="group" :aria-label="t('sys.stormTypes')">
            <p class="label">{{ t('sys.stormTypes') }}</p>
            <label v-for="ty in STORM_TYPES" :key="ty" class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer"><input type="checkbox" :value="ty" v-model="storm.types" @change="applyStorm" :disabled="!can('storm') || busy.storm || (storm.types.length === 1 && storm.types[0] === ty)" class="accent-accent"> {{ t('sys.storm_' + ty) }}</label>
          </div>
          <p v-if="storm.v2 && !storm.uniform" class="text-xs text-warn-ink bg-warn-soft rounded-lg px-2.5 py-1.5">{{ t('sys.stormMixed') }}</p>
        </div>
        <p v-else class="hint">{{ t('common.off') }}</p>
      </Section>
      <Section :title="t('sys.igmp')" icon="activity" :state="st.igmp" :tip="igmp.v2 ? t('sys.igmpTipV2') : t('sys.igmpTip')" compact :locked="locked('igmp')">
        <template #actions><Toggle v-model="igmp.enabled" :disabled="!can('igmp')" :label="t('sys.igmp')" @update:model-value="applyIgmp" /></template>
        <div v-if="igmp.enabled" class="space-y-1.5">
          <label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer"><input type="checkbox" v-model="igmp.fast_leave" @change="applyIgmp" :disabled="!can('igmp')" class="accent-accent"> {{ t('sys.fastLeave') }}</label>
          <label v-if="igmp.v2" class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer"><input type="checkbox" v-model="igmp.report_flood" @change="applyIgmp" :disabled="!can('igmp')" class="accent-accent"> {{ t('sys.reportFlood') }}</label>
          <label v-else class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer"><input type="checkbox" v-model="igmp.querier" @change="applyIgmp" :disabled="!can('igmp')" class="accent-accent"> {{ t('sys.querier') }}</label>
        </div>
        <p v-else class="hint">{{ t('common.off') }}</p>
      </Section>
      <Section :title="t('sys.eee')" icon="bolt" :state="st.eee" :tip="t('sys.eeeTip')" :unsupported="st.eee === 'unsupported'" compact :locked="locked('eee')">
        <template #actions><Toggle v-if="st.eee === 'ok'" v-model="eee.enabled" :disabled="!can('eee')" :label="t('sys.eee')" @update:model-value="applyEee" /></template>
        <p class="hint">{{ eee.enabled ? t('common.on') : t('common.off') }}</p>
      </Section>
    </div>

    <!-- Mirror + loop -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <Section :title="t('sys.mirror')" icon="mirror" :state="st.mirror" :tip="t('sys.mirrorTip')" :locked="locked('mirror')">
        <template #actions><Badge :tone="mirror.enabled ? 'ok' : 'neutral'" dot>{{ mirror.enabled ? t('common.on') : t('sys.mirrorDisabled') }}</Badge></template>
        <div class="space-y-4">
          <div>
            <label class="label" for="sys-mirror-dest">1 · {{ t('sys.mirrorDest') }}</label>
            <select id="sys-mirror-dest" v-model.number="mirror.monitoring_port" :disabled="!can('mirror')" class="select select-sm">
              <option :value="0">{{ t('sys.mirrorDisabled') }}</option>
              <option v-for="p in 10" :key="p" :value="p">{{ t('mac.port') }} {{ p }}{{ p >= 9 ? ' (SFP+)' : '' }}</option>
            </select>
            <p class="hint mt-1">{{ t('sys.mirrorDestDesc') }}</p>
          </div>
          <div>
            <p id="sys-mirror-src-label" class="label">2 · {{ t('sys.mirrorSrc') }}</p>
            <div class="flex flex-wrap gap-1.5" role="group" aria-labelledby="sys-mirror-src-label">
              <button v-for="p in 10" :key="p" type="button" v-show="p !== mirror.monitoring_port" :disabled="!can('mirror')" :aria-pressed="mirror.mirrored_ports.includes(p)" @click="toggleMirrorPort(p)"
                class="chip border transition" :class="mirror.mirrored_ports.includes(p) ? 'bg-accent-soft border-accent/40 text-accent-ink' : 'bg-surface-2 border-line text-muted hover:border-line-strong'">P{{ p }}</button>
            </div>
            <p class="hint mt-1">{{ t('sys.mirrorSrcDesc') }}</p>
          </div>
          <div class="flex items-center justify-between gap-3 flex-wrap">
            <div class="flex gap-4">
              <label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer"><input type="checkbox" v-model="mirror.ingress" :disabled="!can('mirror')" class="accent-accent"> {{ t('sys.mirrorIngress') }}</label>
              <label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer"><input type="checkbox" v-model="mirror.egress" :disabled="!can('mirror')" class="accent-accent"> {{ t('sys.mirrorEgress') }}</label>
            </div>
            <Btn v-if="can('mirror')" size="sm" variant="primary" :loading="busy.mirror" @click="applyMirror">{{ t('sys.mirrorApply') }}</Btn>
          </div>
        </div>
      </Section>

      <Section :title="t('sys.loop')" icon="loop" :state="st.loop" :tip="loopV2 ? t('sys.loopTipV2') : t('sys.loopTip')" :locked="locked('loop')">
        <template v-if="loopV2" #actions><Toggle :model-value="loopCfg.enabled" :disabled="!can('loop')" :label="t('sys.loop')" @update:model-value="v => applyLoop(v ? { enabled: true, interval: loopCfg.interval, recovery: loopCfg.recovery } : { enabled: false })" /></template>
        <!-- 2.0.0.x: one setting for the whole switch; the ports only show where a loop was seen -->
        <template v-if="loopV2">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label class="sm:col-span-2 flex items-center gap-2 text-sm text-ink-2 cursor-pointer"><input type="checkbox" v-model="loopCfg.prevention" @change="applyLoop({ prevention: loopCfg.prevention })" :disabled="!can('loop')" class="accent-accent"> {{ t('sys.loopPrevention') }}</label>
            <!-- the switch only shows its timers while detection runs (they read 0 otherwise): while it is off
                 they are kept here and sent with the toggle that turns it on -->
            <div><label class="label" for="sys-loop-interval">{{ t('sys.loopInterval') }}</label><input id="sys-loop-interval" v-model.number="loopCfg.interval" type="number" min="0" max="100" @change="loopCfg.enabled && applyLoop({ interval: loopCfg.interval })" :disabled="!can('loop')" class="input input-sm num" /></div>
            <div><label class="label" for="sys-loop-recovery">{{ t('sys.loopRecovery') }}</label><input id="sys-loop-recovery" v-model.number="loopCfg.recovery" type="number" min="0" max="100" @change="loopCfg.enabled && applyLoop({ recovery: loopCfg.recovery })" :disabled="!can('loop')" class="input input-sm num" /></div>
            <p v-if="!loopCfg.enabled" class="hint sm:col-span-2">{{ t('sys.loopTimersOff') }}</p>
          </div>
          <div class="grid grid-cols-5 gap-2 mt-4">
            <div v-for="lp in loopCfg.ports" :key="lp.port" class="rounded-lg border-2 py-2 text-center text-xs font-semibold"
              :class="lp.violation ? 'border-danger bg-danger-soft text-danger-ink' : (loopCfg.enabled ? 'border-ok/60 bg-ok-soft text-ok-ink' : 'border-line text-muted')">
              {{ lp.port >= 9 ? 'SFP+' : 'P' }}{{ lp.port }}
              <div class="text-[10px] font-normal">{{ lp.violation ? t('sys.loopViolation') : (loopCfg.enabled ? t('common.on') : t('common.off')) }}</div>
            </div>
          </div>
          <p class="hint mt-3 flex items-start gap-1.5"><Icon name="info" :size="13" class="mt-0.5 shrink-0" />{{ t('sys.loopStpExclusive') }}</p>
        </template>
        <template v-else>
          <p class="hint mb-3">{{ t('sys.loopDesc') }}</p>
          <div class="grid grid-cols-5 gap-2">
            <button v-for="lp in loop" :key="lp.port" type="button" :disabled="!can('loop')" :aria-pressed="!!lp.enabled" @click="toggleLoop(lp)"
              class="rounded-lg border-2 py-2 text-center text-xs font-semibold transition"
              :class="lp.enabled ? (lp.violation ? 'border-danger bg-danger-soft text-danger-ink' : 'border-ok/60 bg-ok-soft text-ok-ink') : 'border-line text-muted hover:border-line-strong'">
              {{ lp.port >= 9 ? 'SFP+' : 'P' }}{{ lp.port }}
              <div class="text-[10px] font-normal">{{ lp.violation ? t('sys.loopViolation') : (lp.enabled ? t('common.on') : t('common.off')) }}</div>
            </button>
          </div>
        </template>
      </Section>
    </div>

    <!-- Snapshots + change log -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <Section :title="t('sys.snapshots')" icon="snapshot" :state="st.snapshots" :tip="t('sys.snapshotsTip')">
        <template #actions>
          <label v-if="auth.isAdmin" class="inline-flex"><input type="file" accept=".json" class="hidden" @change="importFile"><Btn size="sm" icon="upload" tag="span" class="cursor-pointer">{{ t('sys.snapshotImport') }}</Btn></label>
          <Btn v-if="auth.isAdmin" size="sm" variant="primary" icon="plus" @click="showSave = true">{{ t('sys.snapshotSave') }}</Btn>
        </template>
        <ul v-if="snapshots.length" class="divide-y divide-line -mx-5">
          <li v-for="s in snapshots" :key="s.id" class="px-5 py-2.5 flex items-center gap-3 group">
            <Icon name="snapshot" :size="16" class="text-muted shrink-0" />
            <div class="min-w-0 flex-1"><p class="text-sm font-medium text-ink truncate">{{ s.name }}</p><p class="text-[11px] text-muted num">{{ fmtDate(s.created_at) }}</p></div>
            <div class="flex gap-0.5">
              <Btn variant="ghost" size="xs" icon="eye" icon-only :aria-label="t('sys.snapshotView')" @click="viewSnapshot(s)" />
              <Btn variant="ghost" size="xs" icon="download" icon-only :aria-label="t('sys.snapshotDownload')" @click="downloadSnapshot(s)" />
              <Btn v-if="auth.isAdmin" variant="ghost" size="xs" icon="trash" icon-only :aria-label="t('sys.snapshotDelete')" class="hover:text-danger" @click="deleteSnapshot(s)" />
            </div>
          </li>
        </ul>
        <EmptyState v-else compact icon="snapshot" :title="t('sys.snapshotNone')" />
      </Section>

      <Section id="changes" :title="t('sys.changes')" icon="history" :state="st.changes" :tip="t('sys.changesDesc')">
        <ul v-if="changes.length" class="divide-y divide-line -mx-5 max-h-80 overflow-auto">
          <li v-for="c in changes" :key="c.id" class="px-5 py-2 flex items-start gap-3 text-sm">
            <span class="w-6 h-6 rounded bg-surface-3 text-muted flex items-center justify-center shrink-0 mt-0.5"><Icon name="history" :size="13" /></span>
            <div class="min-w-0 flex-1">
              <p class="text-ink">{{ t('changes.' + c.action) }} <span class="text-muted">· {{ c.username || '?' }}</span></p>
              <p v-if="c.details" class="text-[11px] text-muted mono truncate" :title="JSON.stringify(c.details)">{{ JSON.stringify(c.details) }}</p>
            </div>
            <span class="text-[11px] text-muted num shrink-0">{{ fmtDate(c.created_at) }}</span>
          </li>
        </ul>
        <EmptyState v-else compact icon="history" :title="t('swdash.noChanges')" />
      </Section>
    </div>

    <!-- Danger zone -->
    <div v-if="can('reboot')" class="card border-danger/40">
      <div class="card-head items-center flex-wrap">
        <div class="min-w-0"><h3 class="h2 text-danger-ink">{{ t('sys.danger') }}</h3><p class="hint">{{ t('sys.dangerDesc') }}</p></div>
        <Btn variant="danger-soft" icon="power" @click="doReboot">{{ t('sys.reboot') }}</Btn>
      </div>
    </div>

    <Modal :open="showSave" :title="t('sys.snapshotSave')" width="sm" @close="showSave = false">
      <form id="snap-form" @submit.prevent="saveSnapshot"><input v-model.trim="snapshotName" required maxlength="64" :placeholder="t('sys.snapshotName')" :aria-label="t('sys.snapshotSave')" class="input" autofocus /></form>
      <template #footer><Btn @click="showSave = false">{{ t('common.cancel') }}</Btn><Btn variant="primary" type="submit" form="snap-form" :disabled="!snapshotName" :loading="busy.snapshot">{{ t('common.save') }}</Btn></template>
    </Modal>
    <Modal :open="!!viewing" :title="viewing?.name || ''" :subtitle="viewing ? fmtDate(viewing.created_at) : ''" width="lg" @close="viewing = null">
      <pre class="text-xs bg-surface-2 border border-line rounded-lg p-4 overflow-auto max-h-[60vh] mono text-ink-2">{{ JSON.stringify(viewing?.config, null, 2) }}</pre>
    </Modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, defineComponent, h } from 'vue'
import { api } from '../composables/useApi.js'
import { useToast } from '../composables/useToast.js'
import { useConfirm } from '../composables/useConfirm.js'
import { useAuthStore } from '../stores/auth.js'
import { useSwitchesStore } from '../stores/switches.js'
import { useI18n } from '../i18n/index.js'
import Tip from '../components/Tip.vue'
import Btn from '../components/ui/Btn.vue'
import Badge from '../components/ui/Badge.vue'
import Toggle from '../components/ui/Toggle.vue'
import Icon from '../components/ui/Icon.vue'
import Modal from '../components/ui/Modal.vue'
import EmptyState from '../components/ui/EmptyState.vue'

const props = defineProps({ switchId: Number })
const { t, locale } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()
const sw = useSwitchesStore()
// admin and the setting is changeable on this switch's firmware (2.0.0.x: see read_only from the backend)
const can = (feature) => auth.isAdmin && !sw.readOnly(feature)
const locked = (feature) => auth.isAdmin && sw.readOnly(feature)
const base = `/api/switches/${props.switchId}`

// per-section load state: loading | ok | unsupported | error
const st = reactive({ status: 'loading', time: 'loading', stp: 'loading', storm: 'loading', igmp: 'loading', eee: 'loading', mirror: 'loading', loop: 'loading', snapshots: 'loading', changes: 'loading' })
const busy = reactive({ net: false, sntp: false, time: false, mirror: false, snapshot: false, storm: false })

const info = ref({})
const net = reactive({ dhcp: false, ip: '', netmask: '', gateway: '' })
const swapSfp = ref(false)
// the firmware line usually decides the numbering (1.0.0.x swapped, 2.0.0.x not): flag a setting that does not match
const portMapMismatch = computed(() => typeof info.value.swap_sfp_suggested === 'boolean' && info.value.swap_sfp_suggested !== swapSfp.value)
const moveDescriptions = ref(true)
const timeData = ref({})
const timeMode = ref('sntp')
const sntp = reactive({ enabled: false, server: 'pool.ntp.org', poll: 64 })
const tz = reactive({ time: '', date: '', timezone: '+00:00', daylight: false })
// timezone/daylight as read from the switch; only fields the user changed are posted back
const tzLoaded = reactive({ timezone: '+00:00', daylight: false })
const sntpStatus = ref(null)
const sntpResolved = ref('')
const stp = reactive({ enabled: false, mode: 'stp' })
// 2.0.0.x (v2): rate in Mbps per traffic type; uniform is false when the ports differ (set on the switch)
const STORM_TYPES = ['broadcast', 'multicast', 'unknown_unicast', 'unknown_multicast']
const storm = reactive({ enabled: false, rate: 100, v2: false, types: ['broadcast'], uniform: true })
// 2.0.0.x (v2): report flooding instead of a global querier
const igmp = reactive({ enabled: false, fast_leave: true, querier: false, v2: false, report_flood: false })
const eee = reactive({ enabled: false })
const mirror = reactive({ monitoring_port: 0, enabled: false, ingress: true, egress: true, mirrored_ports: [] })
const loop = ref([])
// 2.0.0.x: loop detection is one setting for the whole switch
const loopV2 = ref(false)
const loopCfg = reactive({ enabled: false, prevention: false, interval: 0, recovery: 0, ports: [] })
const snapshots = ref([])
const changes = ref([])
const showSave = ref(false)
const snapshotName = ref('')
const viewing = ref(null)

const TZ = ['-12:00', '-11:00', '-10:00', '-09:30', '-09:00', '-08:00', '-07:00', '-06:00', '-05:00', '-04:00', '-03:30', '-03:00', '-02:00', '-01:00', '+00:00', '+01:00', '+02:00', '+03:00', '+03:30', '+04:00', '+04:30', '+05:00', '+05:30', '+05:45', '+06:00', '+06:30', '+07:00', '+08:00', '+08:45', '+09:00', '+09:30', '+10:00', '+10:30', '+11:00', '+12:00', '+12:45', '+13:00', '+14:00']
// The switch may report an offset outside the list: keep it selectable instead of silently falling back to +00:00
const tzOptions = computed(() => tz.timezone && !TZ.includes(tz.timezone) ? [...TZ, tz.timezone] : TZ)
// Only the timezone/daylight fields the user actually changed; the backend keeps the switch's current values for omitted ones
function tzChanges() {
  const body = {}
  if (tz.timezone !== tzLoaded.timezone) body.timezone = tz.timezone
  if (tz.daylight !== tzLoaded.daylight) body.daylight = tz.daylight ? '1' : '0'
  return body
}

function fmtDate(d) { return d ? new Date(d + 'Z').toLocaleString(locale.value, { dateStyle: 'medium', timeStyle: 'short' }) : '' }
function ok(m) { toast.success(m) }
function fail(e) { toast.error(e.message || String(e)) }
function warn(res) { for (const w of res?.warnings || []) toast.error(w) }

// A card whose body reflects the section's own load state
const Section = defineComponent({
  props: { title: String, icon: String, state: String, tip: String, unsupported: Boolean, compact: Boolean, id: String, locked: Boolean },
  setup(p, { slots }) {
    return () => h('section', { class: 'card flex flex-col', id: p.id }, [
      // flex-wrap: on narrow screens the actions drop under the title instead of squeezing it out
      h('div', { class: 'card-head items-center flex-wrap' }, [
        h('div', { class: 'flex items-center gap-2.5 min-w-0' }, [
          h('span', { class: 'w-8 h-8 rounded-lg bg-surface-3 text-muted flex items-center justify-center shrink-0' }, [h(Icon, { name: p.icon || 'info', size: 16 })]),
          h('div', { class: 'min-w-0' }, [
            h('h3', { class: 'h2 inline-flex items-center gap-1.5' }, [p.title, p.tip ? h(Tip, { title: p.title, text: p.tip }) : null]),
          ]),
        ]),
        // read-only on this firmware: say so instead of leaving disabled controls unexplained
        p.locked && p.state === 'ok' ? h(Badge, { tone: 'neutral', class: 'ms-auto', title: t('v2.readOnlyTip') }, () => [h(Icon, { name: 'lock', size: 12 }), ' ', t('v2.readOnly')]) : null,
        slots.actions && p.state === 'ok' ? h('div', { class: ['flex items-center flex-wrap gap-2', p.locked ? '' : 'ms-auto'] }, slots.actions()) : null,
      ]),
      h('div', { class: p.compact ? 'px-5 py-4 flex-1' : 'card-body flex-1' },
        p.state === 'loading' ? [h('div', { class: 'space-y-2 animate-pulse' }, [h('div', { class: 'h-3 rounded bg-surface-3 w-2/3' }), h('div', { class: 'h-3 rounded bg-surface-3 w-1/2' })])]
        : p.state === 'unsupported' ? [h('p', { class: 'text-sm text-muted flex items-center gap-2' }, [h(Icon, { name: 'info', size: 15 }), t('sys.unsupported')])]
        : p.state === 'error' ? [h('p', { class: 'text-sm text-danger-ink flex items-center gap-2' }, [h(Icon, { name: 'x-circle', size: 15 }), t('sys.sectionError')])]
        : slots.default?.()),
    ])
  },
})

async function section(key, fn) {
  st[key] = 'loading'
  try { st[key] = (await fn()) === 'unsupported' ? 'unsupported' : 'ok' }
  catch (e) { st[key] = 'error' }
}

async function loadStatus() {
  const i = await api(`${base}/info`)
  swapSfp.value = !!i.swap_sfp_9_10
  const s = await api(`${base}/status`)
  info.value = s
  net.dhcp = s.dhcpEnabled === '1'; net.ip = s.ipAddress || ''; net.netmask = s.netmask || ''; net.gateway = s.gateway || ''
}
async function loadTime() {
  const d = await api(`${base}/time`)
  if (d.supported === false) return 'unsupported'
  timeData.value = d
  sntp.enabled = d.sntp_state === '1'; sntp.server = d.sntp_server_ip || 'pool.ntp.org'; sntp.poll = parseInt(d.sntp_poll) || 64
  timeMode.value = sntp.enabled ? 'sntp' : 'manual'
  tz.timezone = d.timezoneOffsetVal || '+00:00'
  const dl = Object.entries(d).find(([k]) => k.toLowerCase().includes('daylight'))
  tz.daylight = dl ? ['1', 'on', 'true'].includes(String(dl[1])) : false
  tzLoaded.timezone = tz.timezone; tzLoaded.daylight = tz.daylight
}
async function loadStp() { const d = await api(`${base}/stp`); stp.enabled = !!d.enabled; stp.mode = d.mode || 'stp' }
async function loadStorm() {
  const d = await api(`${base}/storm`)
  storm.v2 = d.model === 'per_port'
  if (storm.v2) {
    storm.enabled = d.enabled; storm.rate = d.rate || 100; storm.uniform = d.uniform
    storm.types = d.types?.length ? [...d.types] : ['broadcast']
  } else {
    storm.enabled = d.sctrl_state === '1'; storm.rate = parseInt(d.sctrl_rate) || 100
  }
}
async function loadIgmp() {
  const d = await api(`${base}/igmp`)
  igmp.enabled = d.config?.igmp === 'on'; igmp.fast_leave = d.config?.fast_leave === 'on'; igmp.querier = d.config?.snoop_querier === 'on'
  const line = sw.current?.firmware_line
  igmp.v2 = line != null ? line >= 2 : 'report_flood' in (d.config || {})
  igmp.report_flood = d.config?.report_flood === 'on'
}
async function loadEee() { const d = await api(`${base}/eee`); if (d.supported === false) return 'unsupported'; eee.enabled = d.enabled ?? d.eee === 'on' }
async function loadMirror() {
  const d = await api(`${base}/mirror`)
  // the destination's own flags are not a source (the switch never mirrors a port to itself)
  const active = d.ports.filter(p => (p.ingress || p.egress) && p.port !== d.monitoring_port)
  mirror.enabled = !!d.enabled
  mirror.monitoring_port = d.enabled ? d.monitoring_port : 0
  mirror.mirrored_ports = active.map(p => p.port)
  mirror.ingress = active.length === 0 || active.some(p => p.ingress)
  mirror.egress = active.length === 0 || active.some(p => p.egress)
}
async function loadLoop() {
  const d = await api(`${base}/loop`)
  loopV2.value = !Array.isArray(d)
  if (loopV2.value) Object.assign(loopCfg, d)
  else loop.value = d
}
async function loadSnapshots() { snapshots.value = await api(`${base}/snapshots`) }
async function loadChanges() { changes.value = await api(`${base}/changes?limit=50`) }

function loadAll() {
  section('status', loadStatus); section('time', loadTime); section('stp', loadStp); section('storm', loadStorm)
  section('igmp', loadIgmp); section('eee', loadEee); section('mirror', loadMirror); section('loop', loadLoop)
  section('snapshots', loadSnapshots); section('changes', loadChanges)
}

// ── Actions ──
async function togglePortMap(value) {
  try {
    await api(`${base}/port-mapping`, { method: 'PUT', body: JSON.stringify({ swap_sfp_9_10: value, move_descriptions: moveDescriptions.value }) })
    ok(t('sys.portMapUpdated')); sw.patch(props.switchId, { swap_sfp_9_10: value }); section('status', loadStatus)
  } catch (e) { fail(e) }
}
async function applyNetwork() {
  const msg = net.dhcp ? t('sys.dhcpConfirm') : t('sys.staticConfirm', { ip: net.ip })
  if (!await confirm({ title: t('sys.mgmtIface'), message: msg + '\n' + t('sys.ipWarning'), danger: true })) return
  busy.net = true
  try {
    const res = await api(`${base}/network`, { method: 'POST', body: JSON.stringify({ dhcp: net.dhcp, ip: net.ip, netmask: net.netmask, gateway: net.gateway }) })
    // res.note is informational (new reachable address / DHCP hint), not an error
    ok(res.note ? `${t('sys.networkApplied')} · ${res.note}` : t('sys.networkApplied'))
    if (res.ip) sw.patch(props.switchId, { ip: res.ip })
    section('status', loadStatus)
  } catch (e) { fail(e) } finally { busy.net = false }
}
async function applySntp(enable) {
  busy.sntp = true
  try {
    const res = await api(`${base}/sntp`, { method: 'POST', body: JSON.stringify({ enabled: enable, server: sntp.server, poll: sntp.poll }) })
    sntpResolved.value = res.resolved_ip !== sntp.server ? res.resolved_ip : ''
    const changes = tzChanges()
    if (Object.keys(changes).length) await api(`${base}/time`, { method: 'POST', body: JSON.stringify(changes) })
    ok(t('sys.sntpUpdated')); section('time', loadTime)
  } catch (e) { fail(e) } finally { busy.sntp = false }
}
async function checkSntp() { try { sntpStatus.value = await api(`${base}/sntp/check`) } catch (e) { fail(e) } }
async function applyTime() {
  busy.time = true
  try {
    if (sntp.enabled) await api(`${base}/sntp`, { method: 'POST', body: JSON.stringify({ enabled: false, server: sntp.server, poll: sntp.poll }) })
    await api(`${base}/time`, { method: 'POST', body: JSON.stringify({ time: tz.time || null, date: tz.date || null, ...tzChanges() }) })
    ok(t('sys.timeSet')); section('time', loadTime)
  } catch (e) { fail(e) } finally { busy.time = false }
}
async function applyStp() {
  try {
    const res = await api(`${base}/stp`, { method: 'POST', body: JSON.stringify({ enabled: stp.enabled, mode: stp.mode }) })
    ok(t('sys.stpUpdated')); warn(res)
    // 2.0.0.x: STP and loop detection are alternatives, as on the switch's own page
    if (res.loop_turned_off) { ok(t('sys.loopTurnedOff')); section('loop', loadLoop) }
  } catch (e) { fail(e); section('stp', loadStp); section('loop', loadLoop) }
}
async function applyStorm() {
  busy.storm = true
  try {
    const body = { enabled: storm.enabled, rate: storm.rate || 100, ...(storm.v2 ? { types: storm.types } : {}) }
    const res = await api(`${base}/storm`, { method: 'POST', body: JSON.stringify(body) })
    ok(t('sys.stormUpdated')); warn(res)
    if (storm.v2) storm.uniform = true
  } catch (e) { fail(e); section('storm', loadStorm) } finally { busy.storm = false }
}
async function applyIgmp() {
  try {
    const body = { enabled: igmp.enabled, fast_leave: igmp.fast_leave, ...(igmp.v2 ? { report_flood: igmp.report_flood } : { querier: igmp.querier }) }
    const res = await api(`${base}/igmp`, { method: 'POST', body: JSON.stringify(body) })
    ok(t('sys.igmpUpdated')); warn(res)
  } catch (e) { fail(e); section('igmp', loadIgmp) }
}
async function applyEee() { try { await api(`${base}/eee`, { method: 'POST', body: JSON.stringify({ enabled: eee.enabled }) }); ok(t('sys.eeeUpdated')) } catch (e) { fail(e); section('eee', loadEee) } }
function toggleMirrorPort(p) { const i = mirror.mirrored_ports.indexOf(p); i >= 0 ? mirror.mirrored_ports.splice(i, 1) : mirror.mirrored_ports.push(p) }
async function applyMirror() {
  busy.mirror = true
  try {
    const res = await api(`${base}/mirror`, { method: 'POST', body: JSON.stringify({ monitoring_port: mirror.monitoring_port, mirrored_ports: mirror.mirrored_ports, ingress: mirror.ingress, egress: mirror.egress }) })
    ok(t('sys.mirrorUpdated')); warn(res); section('mirror', loadMirror)
  } catch (e) { fail(e) } finally { busy.mirror = false }
}
async function toggleLoop(lp) {
  const ports = Object.fromEntries(loop.value.map(l => [l.port, l.port === lp.port ? !l.enabled : l.enabled]))
  try { await api(`${base}/loop`, { method: 'POST', body: JSON.stringify({ ports }) }); ok(t('sys.loopToggle', { port: lp.port, state: !lp.enabled ? t('common.on') : t('common.off') })) } catch (e) { fail(e) }
  section('loop', loadLoop)
}
async function applyLoop(changes) {
  try {
    const res = await api(`${base}/loop`, { method: 'POST', body: JSON.stringify(changes) })
    ok(t('sys.loopUpdated')); warn(res)
    if (res.stp_turned_off) { ok(t('sys.stpTurnedOff')); section('stp', loadStp) }
  } catch (e) { fail(e); section('stp', loadStp) }
  section('loop', loadLoop)
}
async function saveSnapshot() {
  busy.snapshot = true
  try { await api(`${base}/snapshots`, { method: 'POST', body: JSON.stringify({ name: snapshotName.value }) }); showSave.value = false; snapshotName.value = ''; ok(t('sys.snapshotSaved')); section('snapshots', loadSnapshots) }
  catch (e) { fail(e) } finally { busy.snapshot = false }
}
async function viewSnapshot(s) { try { viewing.value = await api(`${base}/snapshots/${s.id}`) } catch (e) { fail(e) } }
async function downloadSnapshot(s) {
  try {
    const full = await api(`${base}/snapshots/${s.id}`)
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(full, null, 2)], { type: 'application/json' })); a.download = `${s.name}.json`; a.click(); URL.revokeObjectURL(a.href)
  } catch (e) { fail(e) }
}
async function deleteSnapshot(s) {
  if (!await confirm({ title: t('sys.snapshotDelete'), message: t('sys.snapshotDeleteConfirm', { name: s.name }), danger: true, confirmText: t('common.delete') })) return
  try { await api(`${base}/snapshots/${s.id}`, { method: 'DELETE' }); ok(t('sys.snapshotDeleted')); section('snapshots', loadSnapshots) } catch (e) { fail(e) }
}
async function importFile(e) {
  const f = e.target.files[0]; e.target.value = ''
  if (!f) return
  try {
    const d = JSON.parse(await f.text())
    await api(`${base}/snapshots/import`, { method: 'POST', body: JSON.stringify({ name: t('sys.snapshotImportName', { name: f.name }).slice(0, 128), config: d.config || d }) })
    ok(t('sys.snapshotImported')); section('snapshots', loadSnapshots)
  } catch (err) { fail(err) }
}
async function doReboot() {
  if (!await confirm({ title: t('sys.reboot'), message: t('sys.rebootConfirm'), danger: true, confirmText: t('sys.reboot') })) return
  try { await api(`${base}/reboot`, { method: 'POST' }); ok(t('sys.rebooting')) } catch (e) { fail(e) }
}

onMounted(loadAll)
</script>
