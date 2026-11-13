/**
 * Locale-aware formatting for dates and numbers.
 *
 * Two defects this module exists to prevent:
 *
 * 1. Calling `toLocaleString()` with no argument formats in the *browser's*
 *    locale, so an English browser shows English dates inside an Arabic UI.
 * 2. Arabic locale data reports Latin digits in some ICU builds, so numbers and
 *    dates look inconsistent with Persian, which does localize. Arabic is
 *    therefore formatted with the `ar-u-nu-arab` locale extension, which
 *    requests Arabic-Indic digits explicitly.
 */

export const ARABIC_NUMERALS = 'ar-u-nu-arab'

/** The locale actually handed to `Intl` for a UI language. */
export function formatLocale(language: string): string {
  return language.startsWith('ar') ? ARABIC_NUMERALS : language
}

export function formatDate(value: string | Date, language: string, withTime = false): string {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(formatLocale(language), {
    dateStyle: 'medium',
    ...(withTime ? { timeStyle: 'short' } : {}),
  }).format(date)
}

export function formatDateTime(value: string | Date, language: string): string {
  return formatDate(value, language, true)
}

export function formatNumber(value: number, language: string, options: Intl.NumberFormatOptions = {}): string {
  return new Intl.NumberFormat(formatLocale(language), options).format(value)
}

export function formatCurrency(value: number, language: string, currency = 'USD'): string {
  return formatNumber(value, language, { style: 'currency', currency, maximumFractionDigits: 4 })
}
