<template>
  <div class="space-y-6">
    <div class="flex items-center gap-2"><h1 class="text-xl font-bold text-gray-900">{{ t('sys.title') }}</h1><Tip :title="t('sys.title')">{{ t('sys.tip') }}</Tip></div>
    <div v-if="loadError" class="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">{{ t('common.failedLoad') }} {{ loadError }}</div>

    <template v-if="loaded">
      <!-- System Info + Network -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">{{ t('sys.system') }}</h3>
          <div v-for="(v, k) in sysInfo" :key="k" class="flex justify-between items-center text-sm py-1">
            <span class="text-gray-500">{{ k }}</span><span class="font-medium text-gray-900">{{ v }}</span>
          </div>
        </div>
        <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <span class="flex items-center gap-2 mb-3"><h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider">{{ t('sys.mgmtIface') }}</h3><Tip :title="t('sys.mgmtIface')">{{ t('sys.mgmtTip') }}</Tip></span>
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-sm text-gray-500">{{ t('sys.dhcp') }}</span>
              <button @click="net.dhcp = !net.dhcp" class="relative w-11 h-6 rounded-full transition-colors duration-200" :class="net.dhcp ? 'bg-emerald-500' : 'bg-gray-300'">
                <span class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200" :class="net.dhcp ? 'translate-x-5' : ''"></span>
              </button>
            </div>
            <template v-if="!net.dhcp">
              <div><label class="text-xs text-gray-500">{{ t('sys.ipAddress') }}</label><input v-model="net.ip" class="inp w-full"/></div>
              <div><label class="text-xs text-gray-500">{{ t('sys.netmask') }}</label><input v-model="net.netmask" class="inp w-full"/></div>
              <div><label class="text-xs text-gray-500">{{ t('sys.gateway') }}</label><input v-model="net.gateway" class="inp w-full"/></div>
            </template>
            <p v-else class="text-xs text-gray-400">{{ t('sys.dhcpAuto') }}</p>
            <button @click="applyNetwork" class="w-full px-4 py-2 bg-amber-600 text-white text-sm rounded-lg hover:bg-amber-700 transition">
              {{ net.dhcp ? t('sys.applyDhcp') : t('sys.applyStatic') }}
            </button>
            <p class="text-[10px] text-red-400">{{ t('sys.ipWarning') }}</p>
          </div>
        </div>
      </div>

      <!-- Time -->
      <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <div class="flex items-center justify-between mb-4">
          <span class="flex items-center gap-2"><h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider">{{ t('sys.clock') }}</h3><Tip :title="t('sys.clock')">{{ t('sys.clockTip') }}</Tip></span>
          <div class="flex items-center gap-3 text-sm">
            <span class="text-gray-500">{{ t('sys.current') }}</span>
            <span class="font-mono font-medium text-gray-900 bg-gray-50 px-3 py-1 rounded-lg">{{ timeData.timeVal || '--:--:--' }}</span>
            <span class="font-mono font-medium text-gray-900 bg-gray-50 px-3 py-1 rounded-lg">{{ timeData.dateVal || '--/--/----' }}</span>
            <span class="text-xs text-gray-400">{{ timeData.timezoneOffsetVal || '' }}</span>
          </div>
        </div>
        <!-- Mode selector -->
        <div class="flex gap-2 mb-4">
          <button @click="timeMode = 'sntp'" class="px-4 py-2 rounded-lg text-sm font-medium border-2 transition"
            :class="timeMode === 'sntp' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-gray-200 text-gray-500 hover:border-gray-300'">
            {{ t('sys.sntpAuto') }}
          </button>
          <button @click="timeMode = 'manual'" class="px-4 py-2 rounded-lg text-sm font-medium border-2 transition"
            :class="timeMode === 'manual' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-gray-200 text-gray-500 hover:border-gray-300'">
            {{ t('sys.manual') }}
          </button>
        </div>
        <!-- SNTP mode -->
        <div v-if="timeMode === 'sntp'" class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label class="text-xs font-medium text-gray-500 mb-1 block">{{ t('sys.ntpServer') }}</label>
            <input v-model="sntp.server" class="inp w-full" placeholder="pool.ntp.org"/>
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500 mb-1 block">{{ t('sys.pollInterval') }}</label>
            <input v-model.number="sntp.poll" type="number" min="30" max="99999" class="inp w-full" placeholder="64"/>
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500 mb-1 block">{{ t('sys.timezone') }}</label>
            <select v-model="setTime.timezone" @change="applyTimezone" class="inp w-full">
              <option value="-05:00">UTC -05 (EST)</option><option value="+00:00">UTC +00 (GMT)</option>
              <option value="+01:00">UTC +01 (CET)</option><option value="+02:00">UTC +02 (CEST)</option><option value="+08:00">UTC +08</option>
            </select>
          </div>
          <div class="flex items-end gap-2">
            <button @click="sntp.enabled = true; applySntp(); applyTimezone()" class="flex-1 px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition">{{ sntp.enabled ? t('sys.updateSntp') : t('sys.enableSntp') }}</button>
            <button @click="checkSntp" class="px-4 py-2 bg-gray-100 text-gray-600 text-sm rounded-lg hover:bg-gray-200 transition">{{ t('sys.check') }}</button>
          </div>
          <div v-if="sntpStatus" class="col-span-3 text-xs flex items-center gap-2 p-2 rounded-lg" :class="sntpStatus.synced ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'">
            <span class="w-2 h-2 rounded-full" :class="sntpStatus.synced ? 'bg-emerald-500' : 'bg-amber-500'"></span>
            <span v-if="sntpStatus.synced">{{ t('sys.sntpSynced') }} &mdash; Server: {{ sntpStatus.server_ip }} &mdash; Time: {{ sntpStatus.time }} {{ sntpStatus.date }}</span>
            <span v-else>{{ t('sys.sntpNotSynced') }} &mdash; Check server IP: {{ sntpStatus.server_ip }}</span>
          </div>
          <p v-if="sntpResolved" class="col-span-3 text-xs text-gray-500">
            {{ t('sys.resolved') }} <span class="font-mono font-medium">{{ sntpResolved }}</span>
          </p>
        </div>
        <!-- Manual mode -->
        <div v-else class="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label class="text-xs font-medium text-gray-500 mb-1 block">{{ t('sys.time') }}</label>
            <input v-model="setTime.time" class="inp w-full" placeholder="14:30:00"/>
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500 mb-1 block">{{ t('sys.date') }}</label>
            <input v-model="setTime.date" class="inp w-full" placeholder="09/04/2026"/>
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500 mb-1 block">{{ t('sys.timezone') }}</label>
            <select v-model="setTime.timezone" class="inp w-full">
              <option value="-05:00">UTC -05 (EST)</option><option value="+00:00">UTC +00 (GMT)</option>
              <option value="+01:00">UTC +01 (CET)</option><option value="+02:00">UTC +02 (CEST)</option><option value="+08:00">UTC +08</option>
            </select>
          </div>
          <div class="flex items-end">
            <button @click="sntp.enabled = false; applySntp(); applyTime()" class="w-full px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition">{{ t('sys.setTime') }}</button>
          </div>
        </div>
      </div>

      <!-- Feature toggles -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <!-- STP -->
        <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <div class="flex items-center justify-between mb-2">
            <span class="flex items-center gap-1"><h3 class="text-sm font-semibold text-gray-700">{{ t('sys.stp') }}</h3><Tip :title="t('sys.stp')">{{ t('sys.stpTip') }}</Tip></span>
            <button @click="stp.enabled = !stp.enabled; applyStp()" class="relative w-11 h-6 rounded-full transition-colors duration-200" :class="stp.enabled ? 'bg-emerald-500' : 'bg-gray-300'">
              <span class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200" :class="stp.enabled ? 'translate-x-5' : ''"></span>
            </button>
          </div>
          <p class="text-xs text-gray-400">{{ t('sys.stpTip') }}</p>
          <select v-if="stp.enabled" v-model="stp.mode" @change="applyStp" class="inp w-full mt-2">
            <option value="stp">{{ t('sys.stpClassic') }}</option><option value="rstp">{{ t('sys.stpRapid') }}</option>
          </select>
        </div>
        <!-- Storm -->
        <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <div class="flex items-center justify-between mb-2">
            <span class="flex items-center gap-1"><h3 class="text-sm font-semibold text-gray-700">{{ t('sys.storm') }}</h3><Tip :title="t('sys.storm')">{{ t('sys.stormTip') }}</Tip></span>
            <button @click="storm.enabled = !storm.enabled; applyStorm()" class="relative w-11 h-6 rounded-full transition-colors duration-200" :class="storm.enabled ? 'bg-emerald-500' : 'bg-gray-300'">
              <span class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200" :class="storm.enabled ? 'translate-x-5' : ''"></span>
            </button>
          </div>
          <p class="text-xs text-gray-400">{{ t('sys.stormTip') }}</p>
          <div v-if="storm.enabled" class="mt-2">
            <label class="text-xs text-gray-500">{{ t('sys.stormRate') }}</label>
            <input v-model.number="storm.rate" type="number" min="1" max="1000" @blur="applyStorm" class="inp w-full"/>
          </div>
        </div>
        <!-- IGMP -->
        <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <div class="flex items-center justify-between mb-2">
            <span class="flex items-center gap-1"><h3 class="text-sm font-semibold text-gray-700">{{ t('sys.igmp') }}</h3><Tip :title="t('sys.igmp')">{{ t('sys.igmpTip') }}</Tip></span>
            <button @click="igmp.enabled = !igmp.enabled; applyIgmp()" class="relative w-11 h-6 rounded-full transition-colors duration-200" :class="igmp.enabled ? 'bg-emerald-500' : 'bg-gray-300'">
              <span class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200" :class="igmp.enabled ? 'translate-x-5' : ''"></span>
            </button>
          </div>
          <p class="text-xs text-gray-400">{{ t('sys.igmpTip') }}</p>
          <div v-if="igmp.enabled" class="mt-2 space-y-1">
            <label class="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input type="checkbox" v-model="igmp.fast_leave" @change="applyIgmp" class="rounded border-gray-300 text-indigo-600"> {{ t('sys.fastLeave') }}
            </label>
            <label class="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input type="checkbox" v-model="igmp.querier" @change="applyIgmp" class="rounded border-gray-300 text-indigo-600"> {{ t('sys.querier') }}
            </label>
          </div>
        </div>
        <!-- EEE -->
        <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <div class="flex items-center justify-between mb-2">
            <span class="flex items-center gap-1"><h3 class="text-sm font-semibold text-gray-700">{{ t('sys.eee') }}</h3><Tip :title="t('sys.eee')">{{ t('sys.eeeTip') }}</Tip></span>
            <button @click="eee.enabled = !eee.enabled; applyEee()" class="relative w-11 h-6 rounded-full transition-colors duration-200" :class="eee.enabled ? 'bg-emerald-500' : 'bg-gray-300'">
              <span class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200" :class="eee.enabled ? 'translate-x-5' : ''"></span>
            </button>
          </div>
          <p class="text-xs text-gray-400">{{ t('sys.eeeTip') }}</p>
        </div>
      </div>

      <!-- Port Mirror - redesigned -->
      <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <div class="flex items-center gap-2 mb-1"><h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider">{{ t('sys.mirror') }}</h3><Tip :title="t('sys.mirror')">{{ t('sys.mirrorTip') }}</Tip></div>
        <p class="text-xs text-gray-400 mb-4">{{ t('sys.mirrorTip') }}</p>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
          <!-- Step 1: Destination -->
          <div>
            <div class="flex items-center gap-2 mb-2">
              <span class="w-6 h-6 bg-indigo-100 text-indigo-700 rounded-full text-xs font-bold flex items-center justify-center">1</span>
              <span class="text-sm font-medium text-gray-700">{{ t('sys.mirrorDest') }}</span>
            </div>
            <select v-model.number="mirror.monitoring_port" class="inp w-full">
              <option :value="0">{{ t('sys.mirrorDisabled') }}</option>
              <option v-for="p in 10" :key="p" :value="p">{{ t('mac.port') }} {{ p }} {{ p >= 9 ? '(SFP+)' : '' }}</option>
            </select>
            <p class="text-[10px] text-gray-400 mt-1">{{ t('sys.mirrorDestDesc') }}</p>
          </div>
          <!-- Step 2: Sources -->
          <div>
            <div class="flex items-center gap-2 mb-2">
              <span class="w-6 h-6 bg-indigo-100 text-indigo-700 rounded-full text-xs font-bold flex items-center justify-center">2</span>
              <span class="text-sm font-medium text-gray-700">{{ t('sys.mirrorSrc') }}</span>
            </div>
            <div class="flex flex-wrap gap-1.5">
              <button v-for="p in 10" :key="p" v-show="p !== mirror.monitoring_port" @click="toggleMirrorPort(p)"
                class="px-2.5 py-1.5 rounded-lg text-xs font-medium border transition"
                :class="mirror.mirrored_ports.includes(p) ? 'bg-indigo-50 border-indigo-300 text-indigo-700' : 'bg-gray-50 border-gray-200 text-gray-400 hover:bg-gray-100'">
                P{{ p }}
              </button>
            </div>
            <p class="text-[10px] text-gray-400 mt-1">{{ t('sys.mirrorSrcDesc') }}</p>
          </div>
          <!-- Step 3: Direction -->
          <div>
            <div class="flex items-center gap-2 mb-2">
              <span class="w-6 h-6 bg-indigo-100 text-indigo-700 rounded-full text-xs font-bold flex items-center justify-center">3</span>
              <span class="text-sm font-medium text-gray-700">{{ t('sys.mirrorDir') }}</span>
            </div>
            <div class="space-y-2">
              <label class="flex items-center gap-2 text-sm cursor-pointer" :class="mirror.ingress === '1' ? 'text-indigo-700' : 'text-gray-400'">
                <input type="checkbox" :checked="mirror.ingress === '1'" @change="mirror.ingress = mirror.ingress === '1' ? '0' : '1'" class="rounded border-gray-300 text-indigo-600">
                {{ t('sys.mirrorIngress') }}
              </label>
              <label class="flex items-center gap-2 text-sm cursor-pointer" :class="mirror.egress === '1' ? 'text-indigo-700' : 'text-gray-400'">
                <input type="checkbox" :checked="mirror.egress === '1'" @change="mirror.egress = mirror.egress === '1' ? '0' : '1'" class="rounded border-gray-300 text-indigo-600">
                {{ t('sys.mirrorEgress') }}
              </label>
            </div>
            <button v-if="mirror.monitoring_port > 0" @click="applyMirror" class="mt-3 w-full px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition">{{ t('sys.mirrorApply') }}</button>
          </div>
        </div>
        <!-- Visual summary -->
        <div v-if="mirror.monitoring_port > 0 && mirror.mirrored_ports.length" class="mt-4 pt-4 border-t border-gray-100">
          <div class="flex items-center gap-3 text-sm text-gray-500">
            <div class="flex gap-1">
              <span v-for="p in mirror.mirrored_ports" :key="p" class="bg-amber-50 text-amber-700 px-2 py-0.5 rounded text-xs font-medium">P{{ p }}</span>
            </div>
            <svg class="w-5 h-5 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg>
            <span class="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded text-xs font-medium">P{{ mirror.monitoring_port }}</span>
            <span class="text-xs text-gray-400">({{ mirror.ingress === '1' ? 'in' : '' }}{{ mirror.ingress === '1' && mirror.egress === '1' ? '+' : '' }}{{ mirror.egress === '1' ? 'out' : '' }})</span>
          </div>
        </div>
      </div>

      <!-- Loop Detection -->
      <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <div class="flex items-center gap-2 mb-2"><h3 class="text-sm font-semibold text-gray-700">{{ t('sys.loop') }}</h3><Tip :title="t('sys.loop')">{{ t('sys.loopTip') }}</Tip></div>
        <p class="text-xs text-gray-400 mb-3">{{ t('sys.loopDesc') }}</p>
        <div class="flex flex-wrap gap-2">
          <button v-for="lp in loop" :key="lp.port" @click="toggleLoop(lp.port)"
            class="px-3 py-2 rounded-lg text-xs font-medium border transition-all"
            :class="lp.enabled ? (lp.violation ? 'bg-red-50 border-red-300 text-red-700' : 'bg-emerald-50 border-emerald-300 text-emerald-700') : 'bg-gray-50 border-gray-200 text-gray-400 hover:bg-gray-100'">
            {{ t('mac.port') }} {{ lp.port }} <span v-if="lp.violation" class="ml-1 animate-pulse">LOOP!</span>
          </button>
        </div>
      </div>

      <!-- Static MAC - redesigned -->
      <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-1">{{ t('sys.staticMac') }}</h3>
        <p class="text-xs text-gray-400 mb-4">{{ t('sys.staticMacTip') }}</p>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
          <div>
            <label class="text-xs font-medium text-gray-500 mb-1 block">{{ t('sys.macAddress') }}</label>
            <input v-model="staticMac.mac" class="inp w-full" placeholder="AA:BB:CC:DD:EE:FF"/>
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500 mb-1 block">{{ t('sys.macPort') }}</label>
            <select v-model.number="staticMac.port" class="inp w-full">
              <option v-for="p in 10" :key="p" :value="p">{{ t('mac.port') }} {{ p }}{{ p >= 9 ? ' (SFP+)' : '' }}</option>
            </select>
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500 mb-1 block">{{ t('sys.macVlanGroup') }}</label>
            <input v-model.number="staticMac.fid" type="number" min="0" max="63" class="inp w-full" placeholder="0"/>
            <p class="text-[10px] text-gray-400 mt-0.5">{{ t('sys.macVlanGroupDesc') }}</p>
          </div>
          <div class="flex items-end">
            <button @click="addStaticMac" class="w-full px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition">{{ t('sys.macAdd') }}</button>
          </div>
        </div>
        <div v-if="staticMacs.length" class="border border-gray-100 rounded-lg overflow-hidden">
          <table class="w-full text-sm">
            <thead class="bg-gray-50"><tr>
              <th class="px-3 py-2 text-left text-xs font-medium text-gray-500">{{ t('sys.macAddress') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium text-gray-500">{{ t('mac.port') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium text-gray-500">{{ t('mac.vlanGroup') }}</th>
            </tr></thead>
            <tbody class="divide-y divide-gray-50">
              <tr v-for="(m, i) in staticMacs" :key="i" class="hover:bg-gray-50">
                <td class="px-3 py-2 font-mono text-gray-700">{{ m.mac }}</td>
                <td class="px-3 py-2"><span class="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded text-xs">{{ t('mac.port') }} {{ m.port }}</span></td>
                <td class="px-3 py-2 text-gray-500">{{ m.fid }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="text-xs text-gray-400 mt-2">{{ t('sys.macNone') }}</p>
      </div>

      <!-- Config Snapshots -->
      <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <div class="flex items-center justify-between mb-3">
          <div>
            <span class="flex items-center gap-2"><h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider">{{ t('sys.snapshots') }}</h3><Tip :title="t('sys.snapshots')">{{ t('sys.snapshotsTip') }}</Tip></span>
            <p class="text-xs text-gray-400">{{ t('sys.snapshotsTip') }}</p>
          </div>
          <div class="flex gap-2">
            <label class="px-3 py-1.5 bg-gray-100 text-gray-600 text-xs rounded-lg hover:bg-gray-200 cursor-pointer">{{ t('sys.snapshotImport') }} <input type="file" accept=".json" @change="importFile" class="hidden"/></label>
            <button @click="showSaveSnapshot = true" class="px-3 py-1.5 bg-indigo-600 text-white text-xs rounded-lg hover:bg-indigo-700">{{ t('sys.snapshotSave') }}</button>
          </div>
        </div>
        <div v-if="snapshots.length" class="divide-y divide-gray-50">
          <div v-for="s in snapshots" :key="s.id" class="flex items-center justify-between py-2 group">
            <div><p class="text-sm font-medium text-gray-900">{{ s.name }}</p><p class="text-xs text-gray-400">{{ formatDate(s.created_at) }}</p></div>
            <div class="flex gap-1.5 opacity-0 group-hover:opacity-100 transition">
              <button @click="viewSnapshot(s)" class="px-2 py-1 text-xs bg-gray-100 rounded hover:bg-gray-200">{{ t('sys.snapshotView') }}</button>
              <button @click="downloadSnapshot(s)" class="px-2 py-1 text-xs bg-indigo-50 text-indigo-600 rounded hover:bg-indigo-100">{{ t('sys.snapshotDownload') }}</button>
              <button @click="deleteSnapshot(s.id)" class="px-2 py-1 text-xs bg-red-50 text-red-600 rounded hover:bg-red-100">{{ t('sys.snapshotDelete') }}</button>
            </div>
          </div>
        </div>
        <p v-else class="text-xs text-gray-400">{{ t('sys.snapshotNone') }}</p>
      </div>

      <!-- Danger -->
      <div class="bg-white rounded-xl border border-red-200 shadow-sm p-5">
        <h3 class="font-semibold text-red-600 mb-2">{{ t('sys.danger') }}</h3>
        <button @click="doReboot" class="px-4 py-2 bg-red-50 text-red-600 text-sm rounded-lg hover:bg-red-100 border border-red-200">{{ t('sys.reboot') }}</button>
      </div>
    </template>

    <!-- Modals -->
    <div v-if="showSaveSnapshot" class="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50" @click.self="showSaveSnapshot = false">
      <div class="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl">
        <h2 class="text-lg font-bold mb-4">{{ t('sys.snapshotSave') }}</h2>
        <form @submit.prevent="saveSnapshot" class="space-y-4">
          <input v-model="snapshotName" required :placeholder="t('sys.snapshotName')" autofocus class="w-full inp"/>
          <div class="flex gap-3">
            <button type="button" @click="showSaveSnapshot = false" class="flex-1 py-2 border rounded-lg text-gray-600 hover:bg-gray-50">{{ t('common.cancel') }}</button>
            <button type="submit" class="flex-1 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">{{ t('common.save') }}</button>
          </div>
        </form>
      </div>
    </div>
    <div v-if="viewing" class="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50" @click.self="viewing = null">
      <div class="bg-white rounded-2xl p-6 w-full max-w-2xl shadow-2xl max-h-[80vh] overflow-auto">
        <div class="flex justify-between mb-4"><h2 class="text-lg font-bold">{{ viewing.name }}</h2>
          <button @click="viewing = null" class="text-gray-400 hover:text-gray-600">X</button></div>
        <pre class="text-xs bg-gray-50 rounded-lg p-4 overflow-auto max-h-[60vh] font-mono">{{ JSON.stringify(viewing.config, null, 2) }}</pre>
      </div>
    </div>

    <p v-if="msg" class="text-sm mt-4" :class="msgOk ? 'text-emerald-600' : 'text-red-500'">{{ msg }}</p>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { api } from '../composables/useApi.js'
import { useToast } from '../composables/useToast.js'
import { useI18n } from '../i18n/index.js'
import Tip from '../components/Tip.vue'

const props = defineProps({ switchId: Number })
const toast = useToast()
const { t } = useI18n()
const loaded = ref(false)
const loadError = ref('')
const sysInfo = ref({})
const netInfo = ref({})
const timeData = ref({})
const timeMode = ref('sntp')
const setTime = reactive({ time: '', date: '', timezone: '+01:00' })
const sntp = reactive({ enabled: false, server: 'pool.ntp.org', poll: 64 })
const stp = reactive({ enabled: false, mode: 'stp' })
const storm = reactive({ enabled: false, rate: 100 })
const igmp = reactive({ enabled: false, fast_leave: true, querier: false })
const eee = reactive({ enabled: false })
const loop = ref([])
const mirror = reactive({ monitoring_port: 0, ingress: '0', egress: '0', mirrored_ports: [] })
const staticMacs = ref([])
const staticMac = reactive({ mac: '', port: 1, fid: 0 })
const snapshots = ref([])
const showSaveSnapshot = ref(false)
const snapshotName = ref('')
const viewing = ref(null)
const net = reactive({ dhcp: true, ip: '', netmask: '', gateway: '' })
const sntpStatus = ref(null)
const sntpResolved = ref('')
const msg = ref('')
const msgOk = ref(true)

function flash(m, ok = true) { ok ? toast.success(m) : toast.error(m) }
function formatDate(d) { return d ? new Date(d + 'Z').toLocaleString() : '' }
function toggleMirrorPort(p) { const i = mirror.mirrored_ports.indexOf(p); i >= 0 ? mirror.mirrored_ports.splice(i, 1) : mirror.mirrored_ports.push(p) }

async function load() {
  try {
    const s = await api(`/api/switches/${props.switchId}/status`)
    sysInfo.value = { Model: s.modle, Firmware: s.fw_ver, Hardware: s.hw_ver, MAC: s.sys_macaddr, Temperature: `${s.temperature}C` }
    netInfo.value = { IPv4: s.ipAddress, Netmask: s.netmask, Gateway: s.gateway, DHCP: s.dhcpEnabled === '1' ? 'On' : 'Off' }
    net.dhcp = s.dhcpEnabled === '1'; net.ip = s.ipAddress; net.netmask = s.netmask; net.gateway = s.gateway
    const t = await api(`/api/switches/${props.switchId}/time`)
    timeData.value = t; sntp.enabled = t.sntp_state === '1'; sntp.server = t.sntp_server_ip || 'pool.ntp.org'; sntp.poll = parseInt(t.sntp_poll) || 64
    timeMode.value = sntp.enabled ? 'sntp' : 'manual'
    setTime.timezone = t.timezoneOffsetVal || '+01:00'
    const st = await api(`/api/switches/${props.switchId}/stp`); stp.enabled = st.enabled; stp.mode = st.mode
    const sc = await api(`/api/switches/${props.switchId}/storm`); storm.enabled = sc.sctrl_state === '1'; storm.rate = parseInt(sc.sctrl_rate)
    const ig = await api(`/api/switches/${props.switchId}/igmp`); igmp.enabled = ig.config.igmp === 'on'; igmp.fast_leave = ig.config.fast_leave === 'on'; igmp.querier = ig.config.snoop_querier === 'on'
    const ee = await api(`/api/switches/${props.switchId}/eee`); eee.enabled = ee.eee === 'on'
    loop.value = await api(`/api/switches/${props.switchId}/loop`)
    const mi = await api(`/api/switches/${props.switchId}/mirror`); mirror.monitoring_port = mi.monitoring_port; mirror.mirrored_ports = mi.ports.filter(p => p.ingress || p.egress).map(p => p.port)
    try { staticMacs.value = await api(`/api/switches/${props.switchId}/mac/static`) } catch(e) {}
    snapshots.value = await api(`/api/switches/${props.switchId}/snapshots`)
    loaded.value = true
  } catch (e) { loadError.value = e.message }
}

async function applyNetwork() {
  if (!net.dhcp && !confirm(t('sys.ipWarning'))) return
  try {
    await api(`/api/switches/${props.switchId}/network`, { method: 'POST', body: JSON.stringify(net) })
    flash(t('sys.networkApplied'))
    await load()
  } catch(e) { flash(e.message, false) }
}
async function applyTime() { try { await api(`/api/switches/${props.switchId}/time`, { method: 'POST', body: JSON.stringify(setTime) }); flash(t('sys.timeSet')); await load() } catch(e) { flash(e.message, false) } }
async function applyTimezone() { try { await api(`/api/switches/${props.switchId}/time`, { method: 'POST', body: JSON.stringify({ timezone: setTime.timezone }) }); flash(t('sys.timezoneSet')); await load() } catch(e) { flash(e.message, false) } }
async function applySntp() {
  try {
    const res = await api(`/api/switches/${props.switchId}/sntp`, { method: 'POST', body: JSON.stringify(sntp) })
    sntpResolved.value = res.resolved_ip !== sntp.server ? res.resolved_ip : ''
    flash(t('sys.sntpUpdated') + (sntpResolved.value ? ` (${t('sys.resolved')} ${sntpResolved.value})` : ''))
  } catch(e) { flash(e.message, false) }
}
async function checkSntp() {
  try {
    sntpStatus.value = await api(`/api/switches/${props.switchId}/sntp/check`)
  } catch(e) { flash(e.message, false) }
}
async function applyStp() { await api(`/api/switches/${props.switchId}/stp`, { method: 'POST', body: JSON.stringify({ enabled: stp.enabled, mode: stp.mode }) }); flash(t('sys.stpUpdated')) }
async function applyStorm() { await api(`/api/switches/${props.switchId}/storm`, { method: 'POST', body: JSON.stringify({ enabled: storm.enabled, rate: storm.rate }) }); flash(t('sys.stormUpdated')) }
async function applyIgmp() { await api(`/api/switches/${props.switchId}/igmp`, { method: 'POST', body: JSON.stringify({ enabled: igmp.enabled, fast_leave: igmp.fast_leave, querier: igmp.querier }) }); flash(t('sys.igmpUpdated')) }
async function applyEee() { await api(`/api/switches/${props.switchId}/eee`, { method: 'POST', body: JSON.stringify({ enabled: eee.enabled }) }); flash(t('sys.eeeUpdated')) }
async function toggleLoop(port) { const lp = loop.value.find(l => l.port === port); lp.enabled = !lp.enabled; const ports = {}; loop.value.forEach(l => ports[l.port] = l.enabled); await api(`/api/switches/${props.switchId}/loop`, { method: 'POST', body: JSON.stringify({ ports }) }); flash(t('sys.loopToggle', { port, state: lp.enabled ? t('common.on') : t('common.off') })) }
async function applyMirror() { await api(`/api/switches/${props.switchId}/mirror`, { method: 'POST', body: JSON.stringify(mirror) }); flash(t('sys.mirrorUpdated')) }
async function addStaticMac() { if (!staticMac.mac) return; await api(`/api/switches/${props.switchId}/mac/static/add`, { method: 'POST', body: JSON.stringify(staticMac) }); flash(t('sys.macAdded')); staticMac.mac = ''; await load() }
async function doReboot() { if (!confirm(t('sys.rebootConfirm'))) return; await api(`/api/switches/${props.switchId}/reboot`, { method: 'POST' }); flash(t('sys.rebooting')) }
async function saveSnapshot() { await api(`/api/switches/${props.switchId}/snapshots`, { method: 'POST', body: JSON.stringify({ name: snapshotName.value }) }); showSaveSnapshot.value = false; snapshotName.value = ''; flash(t('sys.snapshotSaved')); await load() }
async function viewSnapshot(s) { viewing.value = await api(`/api/switches/${props.switchId}/snapshots/${s.id}`) }
async function downloadSnapshot(s) { const full = await api(`/api/switches/${props.switchId}/snapshots/${s.id}`); const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(full, null, 2)])); a.download = `${s.name}.json`; a.click() }
async function deleteSnapshot(id) { if (!confirm(t('sys.snapshotDelete') + '?')) return; await api(`/api/switches/${props.switchId}/snapshots/${id}`, { method: 'DELETE' }); flash(t('sys.snapshotDeleted')); await load() }
async function importFile(e) { const f = e.target.files[0]; if (!f) return; try { const d = JSON.parse(await f.text()); await api(`/api/switches/${props.switchId}/snapshots/import`, { method: 'POST', body: JSON.stringify({ name: `Import: ${f.name}`, config: d.config || d }) }); flash(t('sys.snapshotImported')); await load() } catch(err) { flash(t('common.error'), false) }; e.target.value = '' }

onMounted(load)
</script>

<style scoped>
.inp { padding: 0.375rem 0.75rem; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 0.5rem; font-size: 0.875rem; outline: none; transition: all 0.15s; }
.inp:focus { box-shadow: 0 0 0 2px rgba(99,102,241,0.3); border-color: #6366f1; }
</style>
