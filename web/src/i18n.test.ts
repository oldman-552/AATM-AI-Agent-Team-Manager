import { describe, expect, it } from 'vitest'
import i18n, { resources, rtlLanguages, supportedLanguages } from './i18n'

type Dictionary = Record<string, string>
const dictionaries = resources as unknown as Record<'en' | 'ar' | 'fa', { translation: Dictionary }>

describe('internationalization resources', () => {
  it('supports exactly English, Arabic and Persian', () => {
    expect([...supportedLanguages]).toEqual(['en', 'ar', 'fa'])
    expect(Object.keys(dictionaries)).toEqual(['en', 'ar', 'fa'])
  })

  it('keeps all three translation key sets identical', () => {
    const english = Object.keys(dictionaries.en.translation).sort()
    for (const language of ['ar', 'fa'] as const) {
      expect(Object.keys(dictionaries[language].translation).sort()).toEqual(english)
    }
  })

  it('has no empty translations', () => {
    for (const language of supportedLanguages) {
      for (const [key, value] of Object.entries(dictionaries[language].translation)) {
        expect(`${language}.${key}: '${value}'`).not.toBe(`${language}.${key}: ''`)
      }
    }
  })

  it('keeps Arabic and Persian as distinct translations', () => {
    const differing = Object.keys(dictionaries.en.translation).filter(
      (key) => dictionaries.ar.translation[key] !== dictionaries.fa.translation[key],
    )
    expect(differing.length).toBeGreaterThan(100)
    expect(dictionaries.ar.translation.dashboard).not.toBe(dictionaries.fa.translation.dashboard)
  })

  it('marks Arabic and Persian as RTL and English as LTR', async () => {
    expect([...rtlLanguages]).toEqual(['ar', 'fa'])
    await i18n.changeLanguage('ar')
    expect(i18n.dir('ar')).toBe('rtl')
    expect(i18n.dir('fa')).toBe('rtl')
    expect(i18n.dir('en')).toBe('ltr')
    await i18n.changeLanguage('en')
  })
})
