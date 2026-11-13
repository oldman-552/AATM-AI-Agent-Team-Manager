import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Save, SlidersHorizontal, Undo2 } from 'lucide-react'

import { formatDateTime } from './format'
import { api, AppPreferences } from './api'
import RecoveryPanel from './RecoveryPanel'

type Draft = Omit<AppPreferences, 'updated_at'>

function toDraft(settings: AppPreferences): Draft {
  const { updated_at: _ignored, ...editable } = settings
  return editable
}

/**
 * Server-side preferences. Language and theme are applied locally as soon as
 * they change, and persisted so a restart keeps them.
 */
export default function SettingsView({ onTheme, onLanguage }: {
  onTheme: (theme: 'dark' | 'light') => void
  onLanguage: (language: string) => void
}) {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const [draft, setDraft] = useState<Partial<Draft>>({})
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (settings.data) setDraft(toDraft(settings.data.settings))
  }, [settings.data])

  const update = useMutation({
    mutationFn: (payload: Record<string, string | number>) => api.updateSettings(payload),
    onSuccess: async (result) => {
      setDraft(toDraft(result.settings))
      setSaved(true)
      if (typeof result.settings.language === 'string') onLanguage(result.settings.language)
      if (result.settings.theme === 'dark' || result.settings.theme === 'light') onTheme(result.settings.theme)
      await queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })
  const reset = useMutation({
    mutationFn: api.resetSettings,
    onSuccess: async (result) => {
      setDraft(toDraft(result.settings))
      setSaved(false)
      if (typeof result.settings.language === 'string') onLanguage(result.settings.language)
      if (result.settings.theme === 'dark' || result.settings.theme === 'light') onTheme(result.settings.theme)
      await queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  if (settings.isLoading) return <section className="panel"><p className="form-note">{t('loading')}</p></section>
  if (!settings.data) return <section className="panel"><p className="form-error">{t('requestFailed')}</p></section>

  const value = (key: keyof Draft) => draft[key] ?? settings.data?.settings[key]
  const set = (key: keyof Draft, next: string | number) => {
    setSaved(false)
    setDraft((current) => ({ ...current, [key]: next }))
  }

  return (
    <>
      <section className="view-header">
        <div>
          <span className="eyebrow"><SlidersHorizontal size={12} /> {t('settingsEyebrow')}</span>
          <h2>{t('settingsTitle')}</h2>
          <p>{t('settingsSubtitle')}</p>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header"><div><span className="panel-kicker">{t('settingsPreferences')}</span><h3>{t('settingsPreferencesTitle')}</h3></div></div>
        <div className="settings-grid">
          <label>
            <span>{t('settingsLanguage')}</span>
            <select value={String(value('language'))} onChange={(event) => set('language', event.target.value)}>
              <option value="en">English</option>
              <option value="ar">العربية</option>
              <option value="fa">فارسی</option>
            </select>
          </label>
          <label>
            <span>{t('settingsTheme')}</span>
            <select value={String(value('theme'))} onChange={(event) => set('theme', event.target.value)}>
              <option value="dark">{t('settingsThemeDark')}</option>
              <option value="light">{t('settingsThemeLight')}</option>
            </select>
          </label>
          <label>
            <span>{t('settingsPageSize')}</span>
            <select value={String(value('page_size'))} onChange={(event) => set('page_size', Number(event.target.value))}>
              {[10, 20, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
            </select>
          </label>
          <label>
            <span>{t('settingsPoll')}</span>
            <input type="number" min={10} max={600} value={Number(value('notification_poll_seconds'))}
              onChange={(event) => set('notification_poll_seconds', Number(event.target.value))} />
          </label>
          <label>
            <span>{t('settingsCheckpointRetention')}</span>
            <input type="number" min={1} max={500} value={Number(value('checkpoint_retention'))}
              onChange={(event) => set('checkpoint_retention', Number(event.target.value))} />
          </label>
          <label>
            <span>{t('settingsBackupRetention')}</span>
            <input type="number" min={1} max={100} value={Number(value('backup_retention'))}
              onChange={(event) => set('backup_retention', Number(event.target.value))} />
          </label>
        </div>
        <div className="settings-actions">
          <button className="button button-primary" type="button" disabled={update.isPending} onClick={() => update.mutate({ ...draft } as Record<string, string | number>)}>
            <Save size={13} /> {t('settingsSave')}
          </button>
          <button className="button button-secondary" type="button" disabled={reset.isPending} onClick={() => reset.mutate()}>
            <Undo2 size={13} /> {t('settingsReset')}
          </button>
          {saved && !update.isError && <span className="form-success">{t('settingsSaved')}</span>}
          {update.isError && <span className="form-error">{t('requestFailed')}: {update.error.message}</span>}
        </div>
        {settings.data.settings.updated_at && (
          <p className="form-note">
            {t('settingsUpdatedAt')}: {formatDateTime(String(settings.data.settings.updated_at), i18n.language)}
          </p>
        )}
      </section>

      <section className="panel">
        <div className="panel-header"><div><span className="panel-kicker">{t('settingsSecurity')}</span><h3>{t('settingsSecurityTitle')}</h3></div></div>
        <p className="form-note">{settings.data.note}</p>
      </section>

      <RecoveryPanel />
    </>
  )
}
