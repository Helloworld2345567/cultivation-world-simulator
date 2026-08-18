import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AdminAuthControl from '@/components/AdminAuthControl.vue'
import i18n from '@/locales'
import { useAuthStore } from '@/stores/auth'

function jsonResponse(data: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    json: vi.fn().mockResolvedValue(data),
  } as unknown as Response
}

describe('AdminAuthControl', () => {
  beforeEach(() => {
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.useFakeTimers()
  })

  it('lets a read-only visitor log in and clears the password afterward', async () => {
    const authStore = useAuthStore()
    authStore.$patch({ enabled: true, authenticated: false, hydrated: true })
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({
      enabled: true,
      authenticated: true,
      csrf_token: 'csrf-after-login',
    })) as typeof fetch

    const wrapper = mount(AdminAuthControl, {
      global: { plugins: [i18n] },
    })

    expect(wrapper.text()).toContain('游客·只读')
    await wrapper.get('.admin-auth-control__trigger').trigger('click')
    await wrapper.get('input[type="password"]').setValue('secret')
    await wrapper.get('form').trigger('submit')
    await Promise.resolve()
    await Promise.resolve()
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('管理员·可编辑')
    await wrapper.get('.admin-auth-control__trigger').trigger('click')
    expect((wrapper.get('input[type="password"]').element as HTMLInputElement).value).toBe('')
  })

  it('shows local management mode without asking for a password when auth is disabled', () => {
    useAuthStore().$patch({ enabled: false, authenticated: false, hydrated: true })

    const wrapper = mount(AdminAuthControl, {
      global: { plugins: [i18n] },
    })

    expect(wrapper.text()).toContain('本地管理模式')
    expect(wrapper.find('input[type="password"]').exists()).toBe(false)
    expect(wrapper.get('.admin-auth-control__trigger').attributes('disabled')).toBeDefined()
  })
})
