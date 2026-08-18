import { defineStore } from 'pinia';
import { ref } from 'vue';
import { gameSocket } from '../api/socket';
import { useWorldStore } from './world';
import { useUiStore } from './ui';
import { useAuthStore } from './auth';
import { routeSocketMessage } from './socketMessageRouter';

export const useSocketStore = defineStore('socket', () => {
  const isConnected = ref(false);
  const lastError = ref<string | null>(null);
  
  let cleanupMessage: (() => void) | undefined;
  let cleanupStatus: (() => void) | undefined;

  function init() {
    if (cleanupStatus) return; // Already initialized

    const worldStore = useWorldStore();
    const uiStore = useUiStore();
    const authStore = useAuthStore();

    // Listen for status
    cleanupStatus = gameSocket.onStatusChange((connected) => {
      isConnected.value = connected;
      if (connected) {
        lastError.value = null;
      }
    });

    cleanupMessage = gameSocket.on((data) => {
      routeSocketMessage(data, { worldStore, uiStore, canWrite: authStore.canWrite });
    });

    // Connect socket
    gameSocket.connect();
  }

  function disconnect() {
    if (cleanupMessage) cleanupMessage();
    if (cleanupStatus) cleanupStatus();
    cleanupMessage = undefined;
    cleanupStatus = undefined;
    gameSocket.disconnect();
    isConnected.value = false;
  }

  return {
    isConnected,
    lastError,
    init,
    disconnect
  };
});

