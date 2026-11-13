import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Activity, AlertTriangle, ArrowRightLeft, Banknote, Clock3, Gauge, LoaderCircle,
  MonitorSmartphone, Send, ShieldCheck, UserRoundSearch,
} from 'lucide-react'

import { api, AgentCenterEntry } from './api'
import { formatCurrency, formatDate, formatDateTime } from './format'

/**
 * The Live Agent Control Center renders only recorded state. Where AATM has no
 * data it says so instead of guessing, and controls that the backend cannot
 * honour (opening a browser, for example) are shown as unavailable.
 */
export default function AgentCenterView() {
  const { t, i18n } = useTranslation()
  const center = useQuery({ queryKey: ['agentCenter'], queryFn: api.agentCenter, refetchInterval: 15_000 })

  if (center.isLoading) {
    return <p className="form-note"><LoaderCircle className="spin" size={14} /> {t('loading')}</p>
  }
  if (center.isError || !center.data) return <p className="form-error">{t('loadError')}</p>

  return (
    <>
      <div className="notice-panel">
        <UserRoundSearch size={17} />
        <p>{t('centerNote')}</p>
        <span className="notice-count">{t('centerAgents')}: {center.data.total}</span>
      </div>
      <div className="center-grid">
        {center.data.agents.map((entry) => (
          <CenterCard key={entry.agent_id} entry={entry} language={i18n.language} />
        ))}
      </div>
    </>
  )
}

function CenterCard({ entry, language }: { entry: AgentCenterEntry; language: string }) {
  const { t } = useTranslation()
  const [instructionsOpen, setInstructionsOpen] = useState(false)
  const [text, setText] = useState('')
  const queryClient = useQueryClient()

  const issued = useQuery({
    queryKey: ['instructions', entry.agent_id],
    queryFn: () => api.agentInstructions(entry.agent_id),
    enabled: instructionsOpen,
  })
  const send = useMutation({
    mutationFn: (value: string) => api.issueInstruction(entry.agent_id, value),
    onSuccess: async () => {
      setText('')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['instructions', entry.agent_id] }),
        queryClient.invalidateQueries({ queryKey: ['agentCenter'] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
      ])
    },
  })

  const money = (value: number) => formatCurrency(value, language)

  const seconds = entry.execution_time.seconds
  const duration = seconds === null
    ? t('centerNoData')
    : (() => {
        const hours = Math.floor(seconds / 3600)
        const minutes = Math.floor((seconds % 3600) / 60)
        return hours ? `${hours}h ${minutes}m` : `${minutes}m`
      })()

  return (
    <article className={`panel center-card ${entry.is_manager ? 'manager-card' : ''}`}>
      <div className="center-head">
        <div>
          <span className="panel-kicker">{entry.is_manager ? t('manager') : entry.role}</span>
          <h3>{entry.name}</h3>
        </div>
        <span className={`status-chip`}><span className={`status-dot ${entry.status === 'idle' ? 'online' : entry.status === 'disabled' || entry.status === 'error' ? 'offline' : 'checking'}`} />{entry.status}</span>
      </div>

      <dl className="center-facts">
        <div>
          <dt><Gauge size={13} /> {t('centerCurrentTask')}</dt>
          <dd>{entry.current_task ? entry.current_task.title : <span className="muted">{t('centerIdleNoTask')}</span>}
            {entry.current_task && <span className="state-badge small">{entry.current_task.state}</span>}
          </dd>
        </div>
        <div>
          <dt><Activity size={13} /> {t('centerLatestActivity')}</dt>
          <dd>{entry.latest_activity
            ? <>{entry.latest_activity.summary} <time>{formatDateTime(entry.latest_activity.at, language)}</time></>
            : <span className="muted">{t('centerNoData')}</span>}</dd>
        </div>
        <div>
          <dt><Clock3 size={13} /> {t('centerExecutionTime')}</dt>
          <dd>{duration} <span className="muted">({t('centerWallClock')})</span></dd>
        </div>
        <div>
          <dt><Banknote size={13} /> {t('centerCost')}</dt>
          <dd>
            {entry.usage.cost_source === 'none'
              ? <span className="muted">{t('centerNoUsage')}</span>
              : <>{money(entry.usage.estimated_cost_usd)} <span className="muted">({t('centerEstimated')}, {entry.usage.records} {t('centerRecords')})</span>
                  {entry.usage.confirmed_records === 0 && <span className="center-warn"><AlertTriangle size={12} />{t('centerUnconfirmed')}</span>}</>}
          </dd>
        </div>
        <div>
          <dt><MonitorSmartphone size={13} /> {t('centerBrowser')}</dt>
          <dd>{entry.browser.profiles} {t('centerProfiles')} · <span className="muted">{t('centerAutomationOff')}</span></dd>
        </div>
        <div>
          <dt><ShieldCheck size={13} /> {t('centerAuth')}</dt>
          <dd>{entry.authentication.provider_configured ? `${entry.provider} · ${entry.authentication.model ?? t('centerNoModel')}` : <span className="muted">{t('centerProviderUnset')}</span>}</dd>
        </div>
        {entry.errors.length > 0 && (
          <div className="center-error">
            <dt><AlertTriangle size={13} /> {t('centerErrors')}</dt>
            <dd>{entry.errors.map((item) => `${item.state}: ${item.error}`).join(' · ')}</dd>
          </div>
        )}
        <div>
          <dt><ArrowRightLeft size={13} /> {t('centerLease')}</dt>
          <dd>{entry.leases.held
            ? <>{entry.leases.owner} · {t('centerLeaseUntil')} {entry.leases.expires_at ? formatDateTime(entry.leases.expires_at, language) : t('centerNoData')}</>
            : <span className="muted">{t('centerNoLease')}</span>}</dd>
        </div>
      </dl>

      {entry.history.length > 0 && (
        <div className="center-history">
          <strong>{t('centerHistory')}</strong>
          <ul>
            {entry.history.map((item) => (
              <li key={item.task_id}>
                <span>{item.title}</span>
                <span className="state-badge small">{item.state}</span>
                <time>{formatDate(item.updated_at, language)}</time>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="center-actions">
        <button className="button button-secondary" type="button" onClick={() => setInstructionsOpen((value) => !value)}>
          <Send size={14} />{t('centerSendInstruction')}
        </button>
        <span className="center-unavailable"><MonitorSmartphone size={13} />{t('centerOpenBrowserUnavailable')}</span>
      </div>

      {instructionsOpen && (
        <div className="center-instructions">
          <label className="field">
            <span>{t('centerInstructionLabel')}</span>
            <textarea rows={2} maxLength={20_000} value={text} onChange={(event) => setText(event.target.value)} />
          </label>
          <p className="form-note">{t('centerInstructionNote')}</p>
          <div className="form-actions">
            <button
              className="button button-primary"
              type="button"
              disabled={send.isPending || !text.trim()}
              onClick={() => send.mutate(text.trim())}
            >
              {send.isPending ? t('centerSending') : t('centerRecordInstruction')}
            </button>
          </div>
          {send.isSuccess && <p className="form-success">{t('centerInstructionRecorded')}</p>}
          {send.isError && <p className="form-error">{t('requestFailed')}: {send.error.message}</p>}
          {issued.data?.instructions.length ? (
            <ul className="center-instruction-list">
              {issued.data.instructions.map((item) => (
                <li key={item.id}>
                  <p>{item.instruction}</p>
                  <span className="muted">
                    {formatDateTime(item.created_at, language)} · {item.delivered ? t('centerDelivered') : t('centerNotDelivered')}
                  </span>
                </li>
              ))}
            </ul>
          ) : issued.isLoading ? <p className="form-note">{t('loading')}</p> : <p className="form-note">{t('centerNoInstructions')}</p>}
        </div>
      )}
    </article>
  )
}
