import { httpClient } from '../http';
import type { AuthSessionDTO } from '../../types/api';

export const authApi = {
  fetchSession() {
    return httpClient.get<AuthSessionDTO>('/api/v1/query/auth/session');
  },

  login(password: string) {
    return httpClient.post<AuthSessionDTO>('/api/v1/command/auth/login', { password });
  },

  logout() {
    return httpClient.post<AuthSessionDTO>('/api/v1/command/auth/logout', {});
  },
};
