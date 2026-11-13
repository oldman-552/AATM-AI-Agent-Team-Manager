import { describe, expect, it } from 'vitest'
import i18n, { resources, rtlLanguages, supportedLanguages } from './i18n'

// Import every view so a missing key shows up as a real failure rather than a
// raw key rendered in the browser.
const sourceModules = import.meta.glob('./**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true })

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

  it('defines every translation key the UI actually uses', () => {
    const used = new Set<string>()
    for (const [path, source] of Object.entries(sourceModules)) {
      if (path.endsWith('i18n.ts') || path.endsWith('i18n.test.ts')) continue
      for (const match of String(source).matchAll(/\bt\('([A-Za-z0-9_]+)'/g)) used.add(match[1])
    }
    // Static keys with dynamic suffixes must exist for every known suffix.
    for (const suffix of ['Low', 'Medium', 'High']) used.add(`complexity${suffix}`)
    for (const code of [
      'running_without_agent', 'assigned_with_blocked_dependencies',
      'awaiting_review', 'dependency_cycle', 'rework_stuck',
    ]) used.add(`planFinding_${code}`)

    expect(used.size).toBeGreaterThan(250)
    for (const language of supportedLanguages) {
      const missing = [...used].filter((key) => !(key in dictionaries[language].translation))
      expect({ language, missing }).toEqual({ language, missing: [] })
    }
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
