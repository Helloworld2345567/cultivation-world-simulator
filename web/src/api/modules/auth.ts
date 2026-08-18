import { httpClient } from '../http';
import type { AuthSessionDTO } from '../../types/api';

export const authApi = {
  fetchSession() {
    return httpClient.get<AuthSessionDTO>('/api/auth/session');
  },

  login(password: string) {
    return httpClient.post<AuthSessionDTO>('/api/auth/login', { password });
  },

  logout() {
    return httpClient.post<AuthSessionDTO>('/api/auth/logout', {});
  },
};
