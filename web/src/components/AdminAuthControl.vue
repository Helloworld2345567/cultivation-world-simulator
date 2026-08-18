<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const authStore = useAuthStore()

const expanded = ref(false)
const password = ref('')
const busy = ref(false)
const errorMessage = ref('')

const statusLabel = computed(() => {
  if (!authStore.enabled) return t('ui.admin_auth.local_status')
  if (authStore.authenticated) return t('ui.admin_auth.admin_status')
  return t('ui.admin_auth.visitor_status')
})

function toggleExpanded() {
  if (!authStore.enabled || busy.value) return
  expanded.value = !expanded.value
  errorMessage.value = ''
}

async function handleLogin() {
  const submittedPassword = password.value
  if (!submittedPassword || busy.value) return

  busy.value = true
  errorMessage.value = ''
  try {
    await authStore.login(submittedPassword)
    password.value = ''
    expanded.value = false
  } catch {
    errorMessage.value = t('ui.admin_auth.login_failed')
  } finally {
    busy.value = false
  }
}

async function handleLogout() {
  if (busy.value) return

  busy.value = true
  errorMessage.value = ''
  try {
    await authStore.logout()
    password.value = ''
    expanded.value = false
  } catch {
    errorMessage.value = t('ui.admin_auth.logout_failed')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <aside
    v-if="authStore.hydrated"
    class="admin-auth-control"
    :class="{
      'admin-auth-control--admin': authStore.authenticated,
      'admin-auth-control--local': !authStore.enabled,
    }"
  >
    <button
      class="admin-auth-control__trigger"
      type="button"
      :disabled="!authStore.enabled"
      :aria-expanded="authStore.enabled ? expanded : undefined"
      @click="toggleExpanded"
    >
      <span class="admin-auth-control__dot" aria-hidden="true"></span>
      <span>{{ statusLabel }}</span>
    </button>

    <div v-if="expanded && authStore.enabled" class="admin-auth-control__panel">
      <form v-show="!authStore.authenticated" @submit.prevent="handleLogin">
        <label for="admin-auth-password">{{ t('ui.admin_auth.password_label') }}</label>
        <input
          id="admin-auth-password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          :placeholder="t('ui.admin_auth.password_placeholder')"
          :disabled="busy"
        />
        <button type="submit" :disabled="busy || !password">
          {{ busy ? t('ui.admin_auth.logging_in') : t('ui.admin_auth.login') }}
        </button>
      </form>

      <div v-show="authStore.authenticated" class="admin-auth-control__admin-actions">
        <p>{{ t('ui.admin_auth.admin_hint') }}</p>
        <button type="button" :disabled="busy" @click="handleLogout">
          {{ busy ? t('ui.admin_auth.logging_out') : t('ui.admin_auth.logout') }}
        </button>
      </div>

      <p v-if="errorMessage" class="admin-auth-control__error" role="alert">
        {{ errorMessage }}
      </p>
    </div>
  </aside>
</template>

<style scoped>
.admin-auth-control {
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: 10000;
  color: #f3f0e8;
  font-size: 13px;
}

.admin-auth-control__trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 7px 12px;
  border: 1px solid rgba(255, 196, 112, 0.34);
  border-radius: 999px;
  background: rgba(31, 24, 17, 0.9);
  color: #f3d7aa;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.34);
  backdrop-filter: blur(12px);
  cursor: pointer;
}

.admin-auth-control__trigger:disabled {
  cursor: default;
}

.admin-auth-control--admin .admin-auth-control__trigger {
  border-color: rgba(105, 207, 145, 0.42);
  background: rgba(15, 45, 29, 0.9);
  color: #b8efcd;
}

.admin-auth-control--local .admin-auth-control__trigger {
  border-color: rgba(126, 174, 230, 0.38);
  background: rgba(18, 36, 56, 0.9);
  color: #c5ddf8;
}

.admin-auth-control__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 8px currentColor;
}

.admin-auth-control__panel {
  position: absolute;
  right: 0;
  bottom: calc(100% + 10px);
  width: min(300px, calc(100vw - 36px));
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 12px;
  background: rgba(18, 18, 18, 0.96);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.48);
}

.admin-auth-control form,
.admin-auth-control__admin-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.admin-auth-control label,
.admin-auth-control__admin-actions p {
  margin: 0;
  color: #c8c2b7;
  line-height: 1.4;
}

.admin-auth-control input,
.admin-auth-control__panel button {
  min-height: 36px;
  box-sizing: border-box;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 7px;
}

.admin-auth-control input {
  width: 100%;
  padding: 7px 10px;
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
}

.admin-auth-control__panel button {
  padding: 7px 12px;
  background: rgba(88, 135, 196, 0.28);
  color: #eaf3ff;
  cursor: pointer;
}

.admin-auth-control__panel button:disabled {
  cursor: wait;
  opacity: 0.58;
}

.admin-auth-control__error {
  margin: 10px 0 0;
  color: #ff9b9b;
  line-height: 1.4;
}
</style>
