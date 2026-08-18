import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SystemMenuShell from '@/components/SystemMenuShell.vue'
import { createTestI18n } from '@/__tests__/utils/i18n'

describe('SystemMenuShell', () => {
  it('disables mutating tabs while keeping settings and about available to spectators', () => {
    const wrapper = mount(SystemMenuShell, {
      props: {
        visible: true,
        activeTab: 'settings',
        gameInitialized: true,
        canWrite: false,
      },
      global: {
        plugins: [createTestI18n({
          ui: {
            system_menu_title: 'System Menu',
            start_game: 'Start',
            load_game: 'Load',
            save_game: 'Save',
            character_management: 'Characters',
            llm_settings: 'LLM',
            settings: 'Settings',
            about: 'About',
            other: 'Other',
            close: 'Close',
          },
        })],
        directives: { sound: () => {} },
      },
    })

    const tabs = Object.fromEntries(
      wrapper.findAll('.menu-tabs button').map(button => [button.text(), button]),
    )

    for (const label of ['Start', 'Load', 'Save', 'Characters', 'LLM']) {
      expect(tabs[label].attributes('disabled')).toBeDefined()
    }
    expect(tabs.Settings.attributes('disabled')).toBeUndefined()
    expect(tabs.About.attributes('disabled')).toBeUndefined()
  })
})
