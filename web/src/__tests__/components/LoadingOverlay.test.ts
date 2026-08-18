import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import LoadingOverlay from '@/components/LoadingOverlay.vue'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'

describe('LoadingOverlay', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should render successfully', () => {
    const i18n = createI18n({
      legacy: false,
      locale: 'zh-CN',
      messages: {
        'zh-CN': {
          loading: {
            title: 'Loading',
            subtitle: 'Subtitle',
            phase: {
              chaos: 'Chaos',
            },
            tips_label: 'Tips',
            elapsed: 'Elapsed {seconds}s',
            tips: [],
            unknown_error: 'Unknown error',
            error: 'Error',
            retry: 'Retry',
          },
          common: {
            version: 'Version',
          }
        }
      }
    })

    const wrapper = mount(LoadingOverlay, {
      props: {
        status: null,
        canWrite: false,
      },
      global: {
        plugins: [createPinia(), i18n],
      }
    })

    expect(wrapper.exists()).toBe(true)
  })

  it('hides the mutating retry action from spectators', () => {
    const i18n = createI18n({
      legacy: false,
      locale: 'zh-CN',
      messages: {
        'zh-CN': {
          loading: {
            title: 'Loading',
            subtitle: 'Subtitle',
            phase: { chaos: 'Chaos' },
            tips_label: 'Tips',
            elapsed: 'Elapsed {seconds}s',
            tips: [],
            unknown_error: 'Unknown error',
            error: 'Error',
            retry: 'Retry',
          },
          common: { version: 'Version' },
        },
      },
    })
    const errorStatus = {
      status: 'error' as const,
      phase: 0,
      phase_name: '',
      progress: 0,
      elapsed_seconds: 0,
      error: 'Initialization failed',
      llm_check_failed: false,
      llm_error_message: '',
    }

    const spectator = mount(LoadingOverlay, {
      props: { status: errorStatus, canWrite: false },
      global: { plugins: [createPinia(), i18n] },
    })
    const administrator = mount(LoadingOverlay, {
      props: { status: errorStatus, canWrite: true },
      global: { plugins: [createPinia(), i18n] },
    })

    expect(spectator.find('.retry-btn').exists()).toBe(false)
    expect(administrator.find('.retry-btn').exists()).toBe(true)
  })
})
