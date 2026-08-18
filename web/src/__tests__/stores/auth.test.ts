import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/stores/auth'
import { httpClient } from '@/api/http'

function jsonResponse(data: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    json: vi.fn().mockResolvedValue(data),
  } as unknown as Response
}

function errorResponse(status: number, code: string): Response {
  return {
    ok: false,
    status,
    statusText: status === 401 ? 'Unauthorized' : 'Forbidden',
    json: vi.fn().mockResolvedValue({
      detail: {
        code,
        message: 'Administrator authentication required',
        details: {},
      },
    }),
  } as unknown as Response
}

describe('auth store', () => {
  beforeEach(() => {
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.useFakeTimers()
  })

  it('hydrates an anonymous browser into read-only spectator mode', async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({
      enabled: true,
      authenticated: false,
      csrf_token: null,
    })) as typeof fetch

    const store = useAuthStore()
    await store.hydrate()

    expect(store.hydrated).toBe(true)
    expect(store.isAdmin).toBe(false)
    expect(store.canWrite).toBe(false)
    expect(store.isReadOnly).toBe(true)
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/auth/session'),
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('keeps local deployments writable when administrator authentication is disabled', async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({
      enabled: false,
      authenticated: false,
      csrf_token: null,
    })) as typeof fetch

    const store = useAuthStore()
    await store.hydrate()

    expect(store.isAdmin).toBe(false)
    expect(store.canWrite).toBe(true)
    expect(store.isReadOnly).toBe(false)
  })

  it('fails closed into read-only mode when session hydration fails', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('offline')) as typeof fetch

    const store = useAuthStore()
    await store.hydrate()

    expect(store.hydrated).toBe(true)
    expect(store.canWrite).toBe(false)
    expect(store.isReadOnly).toBe(true)
  })

  it('enters administrator mode after a successful password login', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        enabled: true,
        authenticated: false,
        csrf_token: null,
      }))
      .mockResolvedValueOnce(jsonResponse({
        enabled: true,
        authenticated: true,
        csrf_token: 'csrf-after-login',
      })) as typeof fetch

    const store = useAuthStore()
    await store.hydrate()
    await store.login('correct horse battery staple')

    expect(store.isAdmin).toBe(true)
    expect(store.canWrite).toBe(true)
    expect(store.csrfToken).toBe('csrf-after-login')
    expect(global.fetch).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/auth/login'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ password: 'correct horse battery staple' }),
      }),
    )
  })

  it('sends the authenticated CSRF token with later write requests', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        enabled: true,
        authenticated: true,
        csrf_token: 'csrf-for-writes',
      }))
      .mockResolvedValueOnce(jsonResponse({ saved: true })) as typeof fetch

    const store = useAuthStore()
    await store.login('secret')
    await httpClient.patch('/api/settings', { ui: { locale: 'zh-CN' } })

    expect(global.fetch).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/settings'),
      expect.objectContaining({
        method: 'PATCH',
        credentials: 'include',
        headers: expect.objectContaining({
          'X-CSRF-Token': 'csrf-for-writes',
        }),
      }),
    )
  })

  it('uses the current CSRF token to log out and returns to read-only mode', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        enabled: true,
        authenticated: true,
        csrf_token: 'csrf-before-logout',
      }))
      .mockResolvedValueOnce(jsonResponse({
        enabled: true,
        authenticated: false,
        csrf_token: null,
      })) as typeof fetch

    const store = useAuthStore()
    await store.login('secret')
    await store.logout()

    expect(store.isAdmin).toBe(false)
    expect(store.canWrite).toBe(false)
    expect(store.csrfToken).toBeNull()
    expect(global.fetch).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/auth/logout'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'X-CSRF-Token': 'csrf-before-logout',
        }),
      }),
    )
  })

  it('adds CSRF only to unsafe methods while always including credentials', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        enabled: true,
        authenticated: true,
        csrf_token: 'csrf-all-writes',
      }))
      .mockResolvedValue(jsonResponse({ ok: true })) as typeof fetch

    const store = useAuthStore()
    await store.login('secret')
    await httpClient.post('/post', {})
    await httpClient.patch('/patch', {})
    await httpClient.put('/put', {})
    await httpClient.delete('/delete')
    await httpClient.get('/get')

    const calls = vi.mocked(global.fetch).mock.calls.slice(1)
    for (const [, init] of calls.slice(0, 4)) {
      expect(init).toEqual(expect.objectContaining({ credentials: 'include' }))
      expect(init?.headers).toEqual(expect.objectContaining({
        'X-CSRF-Token': 'csrf-all-writes',
      }))
    }
    expect(calls[4][1]).toEqual(expect.objectContaining({ credentials: 'include' }))
    expect(calls[4][1]?.headers).not.toEqual(expect.objectContaining({
      'X-CSRF-Token': expect.any(String),
    }))
  })

  it('fails closed when a protected request reports an expired administrator session', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        enabled: true,
        authenticated: true,
        csrf_token: 'expired-csrf-token',
      }))
      .mockResolvedValueOnce(errorResponse(401, 'ADMIN_AUTH_REQUIRED')) as typeof fetch

    const store = useAuthStore()
    await store.login('secret')

    await expect(httpClient.post('/api/v1/command/game/pause', {})).rejects.toMatchObject({
      status: 401,
    })
    expect(store.authenticated).toBe(false)
    expect(store.canWrite).toBe(false)
    expect(store.csrfToken).toBeNull()
  })

  it('treats logout as complete when the server session is already gone', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        enabled: true,
        authenticated: true,
        csrf_token: 'stale-csrf-token',
      }))
      .mockResolvedValueOnce(errorResponse(401, 'ADMIN_AUTH_REQUIRED')) as typeof fetch

    const store = useAuthStore()
    await store.login('secret')

    await expect(store.logout()).resolves.toBeUndefined()
    expect(store.authenticated).toBe(false)
    expect(store.canWrite).toBe(false)
    expect(store.csrfToken).toBeNull()
  })
})
