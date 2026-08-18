<script setup lang="ts">
import { defineAsyncComponent, ref, watch } from 'vue'
import type { SystemMenuTab } from '@/stores/ui'
import SystemMenuShell from '@/components/SystemMenuShell.vue'

const SystemMenuStartTab = defineAsyncComponent(() => import('@/components/system-menu/tabs/SystemMenuStartTab.vue'))
const SystemMenuLoadTab = defineAsyncComponent(() => import('@/components/system-menu/tabs/SystemMenuLoadTab.vue'))
const SystemMenuSaveTab = defineAsyncComponent(() => import('@/components/system-menu/tabs/SystemMenuSaveTab.vue'))
const SystemMenuCharactersTab = defineAsyncComponent(() => import('@/components/system-menu/tabs/SystemMenuCharactersTab.vue'))
const SystemMenuLlmTab = defineAsyncComponent(() => import('@/components/system-menu/tabs/SystemMenuLlmTab.vue'))
const SystemMenuSettingsTab = defineAsyncComponent(() => import('@/components/system-menu/tabs/SystemMenuSettingsTab.vue'))
const SystemMenuAboutTab = defineAsyncComponent(() => import('@/components/system-menu/tabs/SystemMenuAboutTab.vue'))
const SystemMenuOtherTab = defineAsyncComponent(() => import('@/components/system-menu/tabs/SystemMenuOtherTab.vue'))

const props = withDefaults(defineProps<{
  visible: boolean
  defaultTab?: SystemMenuTab
  gameInitialized: boolean
  closable?: boolean
  canWrite?: boolean
}>(), {
  canWrite: true,
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'llm-ready'): void
  (e: 'return-to-main'): void
  (e: 'exit-game'): void
}>()

const protectedTabs = new Set<SystemMenuTab>(['start', 'load', 'save', 'characters', 'llm'])
const normalizeTab = (tab: SystemMenuTab): SystemMenuTab => (
  !props.canWrite && protectedTabs.has(tab) ? 'settings' : tab
)
const activeTab = ref<SystemMenuTab>(normalizeTab(props.defaultTab || 'load'))

watch(() => props.defaultTab, (newTab) => {
  if (newTab) {
    activeTab.value = normalizeTab(newTab)
  }
})

watch(() => props.visible, (val) => {
  if (val && props.defaultTab) {
    activeTab.value = normalizeTab(props.defaultTab)
  }
})

watch(() => props.canWrite, (canWrite) => {
  if (!canWrite && protectedTabs.has(activeTab.value)) {
    activeTab.value = 'settings'
  }
})
</script>

<template>
  <SystemMenuShell
    :visible="visible"
    :active-tab="activeTab"
    :game-initialized="gameInitialized"
    :closable="closable"
    :can-write="canWrite"
    @close="emit('close')"
    @tab-change="activeTab = $event"
  >
    <SystemMenuStartTab
      v-if="activeTab === 'start'"
      :game-initialized="gameInitialized"
      :can-write="canWrite"
    />

    <SystemMenuLoadTab
      v-else-if="activeTab === 'load'"
      @close="emit('close')"
    />

    <SystemMenuSaveTab
      v-else-if="activeTab === 'save'"
      @close="emit('close')"
    />

    <SystemMenuCharactersTab v-else-if="activeTab === 'characters'" />

    <SystemMenuLlmTab
      v-else-if="activeTab === 'llm'"
      @llm-ready="emit('llm-ready')"
    />

    <SystemMenuSettingsTab v-else-if="activeTab === 'settings'" :readonly="!canWrite" />
    <SystemMenuAboutTab v-else-if="activeTab === 'about'" />

    <SystemMenuOtherTab
      v-else-if="activeTab === 'other'"
      :readonly="!canWrite"
      @return-to-main="emit('return-to-main')"
      @exit-game="emit('exit-game')"
    />
  </SystemMenuShell>
</template>
