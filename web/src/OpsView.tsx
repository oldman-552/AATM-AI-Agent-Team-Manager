import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Activity, Cpu, FileSearch, HardDrive, LoaderCircle, Wallet } from 'lucide-react'

import { api } from './api'
import { formatDateTime, formatNumber } from './format'

/**
 * One operational view for the three things an operator checks together: what
 * happened (audit log), what it cost (usage), and what the machine is doing
 * (resources). Every panel states its own provenance; nothing is estimated
 * silently and no recommendation here is applied automatically.
 */
/** A nullable ratio rendered as a percentage, or as "no data" when unmeasurable. */
function ratio(value: number | null, language: string, alreadyPercent = false): string {
  if (value === null || Number.isNaN(value)) return '—'
  const percent = alreadyPercent ? value : value * 100
  return `${formatNumber(Math.round(percent), language)}%`
}

export default function OpsView() {
  // One `useTranslation` for the whole view: calling a hook inside the map below
  // would break the Rules of Hooks.
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const [filter, setFilter] = useState('')

  const events = useQuery({ queryKey: ['events'], queryFn: api.events, refetchInterval: 20_000 })
  const resources = useQuery({ queryKey: ['resources'], queryFn: () => api.resources(), refetchInterval: 15_000 })
  const usage = useQuery({ queryKey: ['usage'], queryFn: api.usage, refetchInterval: 30_000 })

  return (
    <>
      <section className="panel">
        <div className="panel-heading">
          <div><span className="panel-kicker">{t('opsAuditKicker')}</span><h3>{t('opsAuditTitle')}</h3></div>
          <span className="panel-icon"><FileSearch size={17} /></span>
        </div>
        <p className="panel-note">{t('opsAuditNote')}</p>
        <label className="field">
          <span>{t('opsAuditFilter')}</span>
          <input value={filter} maxLength={80} placeholder={t('opsAuditFilterPlaceholder')} onChange={(event) => setFilter(event.target.value)} />
        </label>
        {events.isLoading ? <p className="form-note"><LoaderCircle className="spin" size={13} /> {t('loading')}</p>
          : events.isError || !events.data ? <p className="form-error">{t('loadError')}</p>
          : (() => {
              const needle = filter.trim().toLowerCase()
              const rows = needle
                ? events.data.filter((event) =>
                    `${event.event_type} ${event.summary} ${event.entity_type}`.toLowerCase().includes(needle))
                : events.data
              return rows.length ? (
                <ul className="ops-event-list">
                  {rows.map((event) => (
                    <li key={event.id}>
                      <span className="ops-event-type">{event.event_type}</span>
                      <span className="ops-event-summary">{event.summary}</span>
                      <small>{formatDateTime(event.created_at, language)}</small>
                    </li>
                  ))}
                </ul>
              ) : <p className="form-note">{t('opsAuditEmpty')}</p>
            })()}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div><span className="panel-kicker">{t('opsUsageKicker')}</span><h3>{t('opsUsageTitle')}</h3></div>
          <span className="panel-icon"><Wallet size={17} /></span>
        </div>
        {usage.isLoading ? <p className="form-note">{t('loading')}</p>
          : usage.isError || !usage.data ? <p className="form-error">{t('loadError')}</p>
          : (
            <>
              <p className="panel-note">{usage.data.billing_note}</p>
              <div className="ops-counts">
                <div><span>{t('opsUsageRecords')}</span><strong>{formatNumber(usage.data.total_records, language)}</strong></div>
                {Object.entries(usage.data.by_provider).map(([provider, item]) => (
                  <div key={provider}>
                    <span>{provider}</span>
                    <strong>{formatNumber(item.requests, language)}</strong>
                    <small>
                      {formatNumber(item.estimated_cost_usd, language, { style: 'currency', currency: 'USD' })} {t('intelligenceEstimate')}
                    </small>
                  </div>
                ))}
              </div>
              {usage.data.total_records === 0 && <p className="form-note">{t('opsUsageEmpty')}</p>}
            </>
          )}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div><span className="panel-kicker">{t('opsResourceKicker')}</span><h3>{t('opsResourceTitle')}</h3></div>
          <span className="panel-icon"><Cpu size={17} /></span>
        </div>
        {resources.isLoading ? <p className="form-note">{t('loading')}</p>
          : resources.isError || !resources.data ? <p className="form-error">{t('loadError')}</p>
          : (
            <>
              <p className="panel-note">{resources.data.telemetry}</p>
              <div className="ops-counts">
                <div><span><Cpu size={11} /> CPU</span><strong>{ratio(resources.data.snapshot.cpu_percent, language, true)}</strong></div>
                <div><span><HardDrive size={11} /> {t('opsMemory')}</span><strong>{ratio(resources.data.snapshot.memory_used_ratio, language)}</strong></div>
                <div><span><HardDrive size={11} /> {t('opsDisk')}</span><strong>{ratio(resources.data.snapshot.disk_used_ratio, language)}</strong></div>
                <div>
                  <span><Activity size={11} /> {t('opsConcurrency')}</span>
                  <strong>{resources.data.recommendation.recommended_concurrency} <small>/ {resources.data.recommendation.configured_max}</small></strong>
                  <small>{t('opsAdvisoryOnly')}</small>
                </div>
              </div>
              <ul className="ops-reasons">
                {resources.data.recommendation.reasons.map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
              <p className="form-note">{resources.data.recommendation.note}</p>
            </>
          )}
      </section>
    </>
  )
}
