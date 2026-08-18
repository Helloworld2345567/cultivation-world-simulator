<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import type { Component } from 'vue'

import { useAvatarOverviewStore } from '@/stores/avatarOverview'
import { useAuthStore } from '@/stores/auth'
import PhenomenonSelectorModal from '@/components/game/panels/PhenomenonSelectorModal.vue'

const RankingModal = defineAsyncComponent(() => import('@/components/game/panels/RankingModal.vue'))
const TournamentModal = defineAsyncComponent(() => import('@/components/game/panels/TournamentModal.vue'))
const SectRelationsModal = defineAsyncComponent(() => import('@/components/game/panels/SectRelationsModal.vue'))
const MortalOverviewModal = defineAsyncComponent(() => import('@/components/game/panels/MortalOverviewModal.vue'))
const DynastyOverviewModal = defineAsyncComponent(() => import('@/components/game/panels/DynastyOverviewModal.vue'))
const HiddenDomainOverviewModal = defineAsyncComponent(() => import('@/components/game/panels/HiddenDomainOverviewModal.vue'))
const WorldInfoModal = defineAsyncComponent(() => import('@/components/game/panels/WorldInfoModal.vue'))
const TimeOverviewModal = defineAsyncComponent(() => import('@/components/game/panels/TimeOverviewModal.vue'))
const AvatarOverviewModal = defineAsyncComponent(() => import('@/components/game/panels/AvatarOverviewModal.vue'))
const WorldSecretModal = defineAsyncComponent(() => import('@/components/game/panels/WorldSecretModal.vue'))

type StatusBarPanelKey =
  | 'time'
  | 'worldInfo'
  | 'ranking'
  | 'tournament'
  | 'sectRelations'
  | 'mortalOverview'
  | 'dynastyOverview'
  | 'hiddenDomain'
  | 'phenomenonSelector'
  | 'avatarOverview'
  | 'worldSecret'

const avatarOverviewStore = useAvatarOverviewStore()
const authStore = useAuthStore()

type StatusBarPanelDefinition = {
  component: Component
  beforeOpen?: () => Promise<void> | void
  requiresWrite?: boolean
}

const panelRegistry: Record<StatusBarPanelKey, StatusBarPanelDefinition> = {
  time: { component: TimeOverviewModal },
  worldInfo: { component: WorldInfoModal },
  ranking: { component: RankingModal },
  tournament: { component: TournamentModal },
  sectRelations: { component: SectRelationsModal },
  mortalOverview: { component: MortalOverviewModal },
  dynastyOverview: { component: DynastyOverviewModal },
  hiddenDomain: { component: HiddenDomainOverviewModal },
  phenomenonSelector: { component: PhenomenonSelectorModal, requiresWrite: true },
  avatarOverview: {
    component: AvatarOverviewModal,
    async beforeOpen() {
      if (!avatarOverviewStore.isLoaded) {
        await avatarOverviewStore.refreshOverview()
      }
    },
  },
  worldSecret: { component: WorldSecretModal },
}

const activePanel = ref<StatusBarPanelKey | null>(null)
const activePanelDefinition = computed(() => (
  activePanel.value
    && (!panelRegistry[activePanel.value].requiresWrite || authStore.canWrite)
    ? panelRegistry[activePanel.value]
    : null
))
const activePanelProps = computed(() => (
  activePanel.value && panelRegistry[activePanel.value].requiresWrite
    ? { canWrite: authStore.canWrite }
    : {}
))

function closeActivePanel() {
  activePanel.value = null
}

async function open(panel: StatusBarPanelKey) {
  const definition = panelRegistry[panel]
  if (definition.requiresWrite && !authStore.canWrite) return
  await definition.beforeOpen?.()
  if (definition.requiresWrite && !authStore.canWrite) return
  activePanel.value = panel
}

watch(() => authStore.canWrite, (canWrite) => {
  if (!canWrite && activePanel.value && panelRegistry[activePanel.value].requiresWrite) {
    closeActivePanel()
  }
})

defineExpose({ open })
</script>

<template>
  <component
    :is="activePanelDefinition.component"
    v-if="activePanelDefinition"
    v-bind="activePanelProps"
    :show="true"
    @update:show="value => { if (!value) closeActivePanel() }"
  />
</template>
