import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Activity, CircleAlert, CircleCheck, Database, HeartPulse, LoaderCircle, ShieldQuestion } from 'lucide-react'

import { api } from './api'
import { formatDateTime, formatNumber } from './format'

/**
 * Recovery capability, stated as it is. A failure that cannot happen in this
 * build (a browser crash) is shown as not applicable rather than as "handled",
 * and only the two recoveries AATM genuinely performs are marked automatic.
 */
export default function RecoveryPanel() {
  const { t, i18n } = useTranslation()
  const recovery = useQuery({ queryKey: ['recovery'], queryFn: api.recovery, refetchInterval: 30_000 })

  return (
    <section className="panel recovery-panel">
      <div className="panel-header">
        <div><span className="panel-kicker">{t('recoveryKicker')}</span><h3>{t('recoveryTitle')}</h3></div>
        <span className="panel-icon"><HeartPulse size={17} /></span>
      </div>
      {recovery.isLoading ? <p className="form-note"><LoaderCircle className="spin" size={13} /> {t('loading')}</p>
        : recovery.isError || !recovery.data ? <p className="form-error">{t('loadError')}</p>
        : (
          <>
            <p className="form-note">{recovery.data.note}</p>
            <div className="recovery-counts">
              <div className={recovery.data.database.ok ? '' : 'attention'}>
                <span><Database size={12} /> {t('recoveryDatabase')}</span>
                <strong>{recovery.data.database.ok ? t('recoveryHealthy') : t('recoveryDegraded')}</strong>
                <small>{formatNumber(recovery.data.database.elapsed_ms, i18n.language)} ms</small>
              </div>
              <div>
                <span><Activity size={12} /> {t('recoveryRecoverable')}</span>
                <strong>{formatNumber(recovery.data.queue.recoverable_tasks, i18n.language)}</strong>
                <small>{t('recoveryRetryCeiling')}: {recovery.data.queue.retry_ceiling}</small>
              </div>
              <div className={recovery.data.queue.exhausted_tasks ? 'attention' : ''}>
                <span><CircleAlert size={12} /> {t('recoveryExhausted')}</span>
                <strong>{formatNumber(recovery.data.queue.exhausted_tasks, i18n.language)}</strong>
                <small>{t('recoveryNeedsHuman')}</small>
              </div>
              <div>
                <span><CircleCheck size={12} /> {t('recoveryAutomatic')}</span>
                <strong>{formatNumber(recovery.data.summary.automatic, i18n.language)}</strong>
                <small>/ {formatNumber(recovery.data.summary.detected, i18n.language)} {t('recoveryDetected')}</small>
              </div>
            </div>

            <table className="builder-table recovery-table">
              <thead>
                <tr><th>{t('recoveryFailure')}</th><th>{t('recoveryDetection')}</th><th>{t('recoveryMode')}</th><th>{t('recoveryAction')}</th></tr>
              </thead>
              <tbody>
                {recovery.data.capabilities.map((item) => (
                  <tr key={item.failure} className={item.handled ? '' : 'recovery-na'}>
                    <td>{item.failure}</td>
                    <td>{item.detected_by}</td>
                    <td>
                      {!item.handled ? <span className="recovery-tag na">{t('recoveryNotApplicable')}</span>
                        : item.automatic ? <span className="recovery-tag auto">{t('recoveryTagAutomatic')}</span>
                        : <span className="recovery-tag manual">{t('recoveryTagManual')}</span>}
                    </td>
                    <td>{item.action}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <p className="form-note"><ShieldQuestion size={12} /> {recovery.data.idempotency}</p>
            <p className="form-note">{t('recoveryCheckedAt')}: {formatDateTime(recovery.data.checked_at, i18n.language)}</p>
            {recovery.data.database.integrity && (
              <p className="form-note">
                {t('recoveryIntegrity')}: {recovery.data.database.integrity.ok ? t('recoveryHealthy') : recovery.data.database.integrity.result}
              </p>
            )}
          </>
        )}
    </section>
  )
}
