<script setup lang="ts">
import GameStartPanel from '@/components/game/panels/system/GameStartPanel.vue'

defineProps<{
  gameInitialized: boolean
  canWrite: boolean
}>()
</script>

<template>
  <GameStartPanel :readonly="gameInitialized || !canWrite" />
</template>
