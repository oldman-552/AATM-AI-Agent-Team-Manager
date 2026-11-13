import { spawnSync } from 'node:child_process'
import { describe, expect, it } from 'vitest'
import i18n, { resources, rtlLanguages, supportedLanguages } from './i18n'
import { formatDate, formatLocale, formatNumber } from './format'

/**
 * Right-to-left correctness has two halves:
 *
 * 1. Layout must use logical properties, so the same stylesheet mirrors itself.
 *    A stray `margin-left` silently breaks Arabic and Persian, and no unit test
 *    of translations would catch it.
 * 2. Direction, dates and numbers must follow the active language.
 *
 * This suite checks both from the real source files, so the guard fails if a
 * physical property is reintroduced.
 */
const tsxFilesAll = import.meta.glob('./**/*.tsx', { query: '?raw', import: 'default', eager: true })

const tsxFiles = tsxFilesAll

const PHYSICAL_ALIGN = /text-align\s*:\s*(left|right)/g

function collect(pattern: RegExp, source: string): string[] {
  return [...source.matchAll(pattern)].map((match) => match[0].trim())
}

describe('right-to-left layout invariants', () => {
  it('has no physical left/right declarations in the stylesheet or the built bundle', () => {
    // The stylesheet check lives in scripts/check-rtl-css.mjs because Vite does
    // not expose plain CSS to `import.meta.glob`. Running it here keeps one
    // definition of the rule and fails the unit suite too.
    const result = spawnSync(process.execPath, ['scripts/check-rtl-css.mjs'], { encoding: 'utf8' })
    expect(result.stderr.trim()).toBe('')
    expect(result.status).toBe(0)
    expect(result.stdout).toContain('0 physical')
  })

  it('never hardcodes a physical text alignment in components', () => {
    const offenders: string[] = []
    for (const [path, source] of Object.entries(tsxFiles)) {
      for (const hit of collect(PHYSICAL_ALIGN, String(source))) offenders.push(`${path}: ${hit}`)
    }
    expect(offenders).toEqual([])
  })

  it('marks Arabic and Persian as RTL and switches direction with the language', async () => {
    expect([...rtlLanguages]).toEqual(['ar', 'fa'])
    expect(rtlLanguages).not.toContain('en')

    await i18n.changeLanguage('ar')
    expect(i18n.dir()).toBe('rtl')
    await i18n.changeLanguage('fa')
    expect(i18n.dir()).toBe('rtl')
    await i18n.changeLanguage('en')
    expect(i18n.dir()).toBe('ltr')
  })

  it('formats dates and numbers in the active locale, not the English one', () => {
    const date = new Date('2026-11-13T10:30:00Z')
    const arabic = formatDate(date, 'ar')
    const persian = formatDate(date, 'fa')
    const english = formatDate(date, 'en')
    expect(arabic).not.toBe(english)
    expect(persian).not.toBe(english)
    // Arabic and Persian must not fall back to a bare Gregorian ASCII string.
    expect(/[\u0600-\u06FF]/.test(arabic)).toBe(true)
    expect(/[\u0600-\u06FF]/.test(persian)).toBe(true)

    const arabicNumber = formatNumber(1234.5, 'ar')
    const persianNumber = formatNumber(1234.5, 'fa')
    expect(arabicNumber).not.toBe('1,234.5')
    expect(persianNumber).not.toBe('1,234.5')
    // Arabic-Indic digits for Arabic: this is the defect the shared formatter fixes.
    expect(/[\u0660-\u0669]/.test(arabicNumber)).toBe(true)
    expect(formatLocale('ar')).toBe('ar-u-nu-arab')
    expect(formatLocale('fa')).toBe('fa')
    expect(formatLocale('en')).toBe('en')

    // Persian uses the Solar Hijri calendar, so it must not print a Gregorian year.
    expect(persian).not.toContain('2026')
  })

  it('does not format dates or numbers inline in components', () => {
    const offenders: string[] = []
    for (const [path, source] of Object.entries(tsxFiles)) {
      if (path.includes('test')) continue
      const text = String(source)
      if (/toLocaleString\(\s*\)/.test(text)) offenders.push(`${path}: toLocaleString() without a locale`)
      if (/toLocaleDateString\(\s*\)/.test(text)) offenders.push(`${path}: toLocaleDateString() without a locale`)
      if (/new Intl\.(DateTimeFormat|NumberFormat)/.test(text)) offenders.push(`${path}: inline Intl formatter (use ./format)`)
    }
    expect(offenders).toEqual([])
  })

  it('keeps both RTL dictionaries fully translated', () => {
    const dictionaries = resources as unknown as Record<string, { translation: Record<string, string> }>
    for (const language of ['ar', 'fa'] as const) {
      const entries = Object.entries(dictionaries[language].translation)
      expect(entries.length).toBeGreaterThan(500)
      // Every value must contain at least one Arabic-script character: a Latin
      // string left behind means a key was copied rather than translated.
      const untranslated = entries.filter(([key]) => {
        const value = dictionaries[language].translation[key]
        if (value === 'AATM' || value === 'JSON' || value === 'SQLite' || value === 'PostgreSQL') return false
        return !/[\u0600-\u06FF]/.test(value)
      })
      expect({ language, untranslated: untranslated.map(([key]) => key) }).toEqual({ language, untranslated: [] })
    }
  })

  it('supports exactly the three required languages', () => {
    expect([...supportedLanguages]).toEqual(['en', 'ar', 'fa'])
  })
})
