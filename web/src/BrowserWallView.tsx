import { FormEvent, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Lock, MonitorSmartphone, Plus, ShieldOff, Trash2, Unlock } from 'lucide-react'

import { api, BrowserProfile } from './api'

/**
 * The Browser Wall shows what actually exists: isolated profile directories and
 * their exclusivity state. It never renders a fake page preview, because AATM
 * does not launch or drive browsers in this build.
 */
export default function BrowserWallView() {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const [formOpen, setFormOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const profiles = useQuery({ queryKey: ['browserProfiles'], queryFn: api.browserProfiles, refetchInterval: 20_000 })
  const agents = useQuery({ queryKey: ['agents'], queryFn: api.agents })

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['browserProfiles'] }),
      queryClient.invalidateQueries({ queryKey: ['events'] }),
    ])
  }
  const create = useMutation({
    mutationFn: api.createBrowserProfile,
    onSuccess: async () => { setFormOpen(false); await invalidate() },
  })
  const lockProfile = useMutation({
    mutationFn: ({ id, by }: { id: string; by: string }) => api.lockBrowserProfile(id, by),
    onSuccess: invalidate,
  })
  const unlockProfile = useMutation({
    mutationFn: (id: string) => api.unlockBrowserProfile(id),
    onSuccess: invalidate,
  })
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteBrowserProfile(id),
    onSuccess: async () => { setConfirmDelete(null); await invalidate() },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    create.mutate({
      name: String(form.get('name') ?? '').trim(),
      label: String(form.get('label') ?? '').trim(),
      agent_id: String(form.get('agent_id') ?? '') || null,
    })
  }

  const bytes = (value: number) => new Intl.NumberFormat(i18n.language).format(value)

  function statusKey(profile: BrowserProfile): string {
    const map: Record<string, string> = {
      created: 'profileCreated', ready: 'profileReady', locked: 'profileLocked', archived: 'profileArchived',
    }
    return map[profile.status] ?? profile.status
  }

  return (
    <>
      <section className="view-header">
        <div>
          <span className="eyebrow"><MonitorSmartphone size={12} /> {t('browserWallEyebrow')}</span>
          <h2>{t('browserWallTitle')}</h2>
          <p>{t('browserWallSubtitle')}</p>
        </div>
        <div className="heading-actions">
          <button className="button button-primary" type="button" onClick={() => setFormOpen((value) => !value)}>
            <Plus size={14} /> {t('profileNew')}
          </button>
        </div>
      </section>

      <div className="callout callout-warning">
        <AlertTriangle size={15} />
        <div>
          <strong>{t('browserWallGapTitle')}</strong>
          <p>{t('browserWallGapBody')}</p>
        </div>
      </div>

      {formOpen && (
        <form className="form-grid two-columns panel" onSubmit={submit}>
          <label className="field"><span>{t('profileName')}</span><input name="name" required maxLength={60} autoFocus /></label>
          <label className="field"><span>{t('profileLabel')}</span><input name="label" maxLength={80} /></label>
          <label className="field field-full"><span>{t('profileOwner')}</span>
            <select name="agent_id" defaultValue="">
              <option value="">{t('profileNoOwner')}</option>
              {agents.data?.filter((agent) => !agent.is_manager).map((agent) => (
                <option key={agent.id} value={agent.id}>{agent.name}</option>
              ))}
            </select>
          </label>
          <p className="form-note field-full"><ShieldOff size={11} /> {t('profileNoCredentials')}</p>
          {create.isError && <p className="form-error field-full">{t('requestFailed')}: {create.error.message}</p>}
          <div className="form-actions field-full">
            <button className="button button-secondary" type="button" onClick={() => setFormOpen(false)}>{t('cancel')}</button>
            <button className="button button-primary" type="submit" disabled={create.isPending}>{t('create')}</button>
          </div>
        </form>
      )}

      {profiles.isLoading ? <p className="form-note">{t('loading')}</p> : profiles.data?.profiles.length ? (
        <div className="record-grid">
          {profiles.data.profiles.map((profile) => (
            <article className={`record-card browser-card ${profile.status}`} key={profile.id}>
              <div className="record-card-top">
                <span className={`record-icon ${profile.status === 'locked' ? 'amber' : 'cyan'}`}><MonitorSmartphone size={18} /></span>
                <span className={`status-chip ${profile.status}`}>
                  <span className={`status-dot ${profile.status === 'locked' ? 'checking' : profile.status === 'archived' ? 'offline' : 'online'}`} />
                  {t(statusKey(profile))}
                </span>
              </div>
              <h3>{profile.label || profile.name}</h3>
              <p className="record-meta">
                {agents.data?.find((agent) => agent.id === profile.agent_id)?.name ?? t('profileNoOwner')}
                {' · '}{t('profileIsolation')}: {profile.isolation === 'shared_readonly' ? t('profileSharedReadonly') : t('profilePerProfile')}
              </p>
              <dl className="browser-facts">
                <div><dt>{t('profileSize')}</dt><dd>{bytes(profile.size_bytes)} B</dd></div>
                <div><dt>{t('profileFiles')}</dt><dd>{bytes(profile.entries)}</dd></div>
                <div><dt>{t('profileSession')}</dt><dd>{t('profileNotInspected')}</dd></div>
              </dl>
              {profile.locked_by && <p className="form-note">{t('profileLockedBy', { name: profile.locked_by })}</p>}
              <div className="record-actions">
                {profile.status === 'locked' ? (
                  <button className="button button-secondary" type="button" disabled={unlockProfile.isPending}
                    onClick={() => unlockProfile.mutate(profile.id)}>
                    <Unlock size={12} /> {t('profileUnlock')}
                  </button>
                ) : (
                  <button className="button button-secondary" type="button" disabled={lockProfile.isPending || profile.status === 'archived'}
                    onClick={() => lockProfile.mutate({ id: profile.id, by: 'local-user' })}>
                    <Lock size={12} /> {t('profileLock')}
                  </button>
                )}
                {confirmDelete === profile.id ? (
                  <>
                    <button className="button button-danger" type="button" disabled={remove.isPending} onClick={() => remove.mutate(profile.id)}>
                      <Trash2 size={12} /> {t('profileConfirmDelete')}
                    </button>
                    <button className="button button-secondary" type="button" onClick={() => setConfirmDelete(null)}>{t('cancel')}</button>
                  </>
                ) : (
                  <button className="button button-secondary" type="button" disabled={profile.status === 'locked'}
                    onClick={() => setConfirmDelete(profile.id)}>
                    <Trash2 size={12} /> {t('delete')}
                  </button>
                )}
              </div>
              {(lockProfile.isError || unlockProfile.isError || remove.isError) && (
                <p className="form-error">{t('requestFailed')}: {(lockProfile.error ?? unlockProfile.error ?? remove.error)?.message}</p>
              )}
            </article>
          ))}
        </div>
      ) : (
        <div className="panel"><p className="form-note">{t('profileEmpty')}</p></div>
      )}
    </>
  )
}
