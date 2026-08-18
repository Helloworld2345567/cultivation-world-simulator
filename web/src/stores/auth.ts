import { computed, ref } from 'vue';
import { defineStore } from 'pinia';

import { authApi } from '@/api/modules/auth';
import { setAdminAuthRequiredHandler, setCsrfToken } from '@/api/http';
import type { AuthSessionDTO } from '@/types/api';

export const useAuthStore = defineStore('auth', () => {
  const hydrated = ref(false);
  // Fail closed until the server tells us authentication is disabled.
  const enabled = ref(true);
  const authenticated = ref(false);
  const csrfToken = ref<string | null>(null);

  const isAdmin = computed(() => authenticated.value);
  const canWrite = computed(() => !enabled.value || authenticated.value);
  const isReadOnly = computed(() => !canWrite.value);

  function applySession(session: AuthSessionDTO) {
    enabled.value = session.enabled;
    authenticated.value = session.authenticated;
    csrfToken.value = session.csrf_token;
    setCsrfToken(session.csrf_token);
  }

  function failClosed() {
    applySession({
      enabled: true,
      authenticated: false,
      csrf_token: null,
    });
  }

  setAdminAuthRequiredHandler(failClosed);

  async function hydrate() {
    try {
      const session = await authApi.fetchSession();
      applySession(session);
    } catch {
      enabled.value = true;
      authenticated.value = false;
      csrfToken.value = null;
      setCsrfToken(null);
    } finally {
      hydrated.value = true;
    }
  }

  async function login(password: string) {
    applySession(await authApi.login(password));
  }

  async function logout() {
    try {
      applySession(await authApi.logout());
    } catch (error) {
      // The shared HTTP client has already failed closed when the backend says
      // this session no longer exists. Treat logout as idempotently complete.
      if (!authenticated.value) return;
      throw error;
    }
  }

  return {
    hydrated,
    enabled,
    authenticated,
    csrfToken,
    isAdmin,
    canWrite,
    isReadOnly,
    hydrate,
    login,
    logout,
  };
});
