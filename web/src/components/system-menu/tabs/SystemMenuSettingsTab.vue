<script setup lang="ts">
import SettingsPanel from '@/components/settings/SettingsPanel.vue'

defineProps<{
  readonly: boolean
}>()
</script>

<template>
  <SettingsPanel :readonly="readonly" />
</template>
