import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { NSelect, NSlider, NSwitch } from 'naive-ui'
import { describe, expect, it } from 'vitest'

import SettingsPanel from '@/components/settings/SettingsPanel.vue'
import { createTestI18n } from '@/__tests__/utils/i18n'

describe('SettingsPanel', () => {
  it('renders every persisted setting control disabled in read-only mode', () => {
    const wrapper = mount(SettingsPanel, {
      props: { readonly: true },
      global: {
        plugins: [createPinia(), createTestI18n({
          ui: {
            settings: 'Settings',
            language: 'Language',
            language_accessible_label: 'Language',
            sound: 'Sound',
            bgm_volume: 'Music',
            sfx_volume: 'Effects',
            auto_save: 'Auto Save',
            auto_save_desc: 'Automatically save',
          },
        })],
      },
    })

    expect(wrapper.getComponent(NSelect).props('disabled')).toBe(true)
    for (const slider of wrapper.findAllComponents(NSlider)) {
      expect(slider.props('disabled')).toBe(true)
    }
    expect(wrapper.getComponent(NSwitch).props('disabled')).toBe(true)
  })
})
