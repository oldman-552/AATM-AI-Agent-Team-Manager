import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Brain, CircleAlert, Info, LoaderCircle, Scale, ShieldCheck } from 'lucide-react'

import { api } from './api'
import { formatNumber } from './format'

/**
 * Measured figures and rule-based assessments sit in separate sections and are
 * labelled as such. Nothing here ranks agents by task count, and a null metric
 * renders as "no data" rather than as zero.
 */
export default function IntelligencePanel() {
  const { t, i18n } = useTranslation()
  const [days, setDays] = useState(90)
  const report = useQuery({ queryKey: ['intelligence', days], queryFn: () => api.intelligence(days) })

  const pct = (value: number | null) =>
    value === null ? <span className="muted">{t('centerNoData')}</span> : `${formatNumber(Math.round(value * 100), i18n.language)}%`

  const secs = (value: number | null) => {
    if (value === null) return <span className="muted">{t('centerNoData')}</span>
    const hours = Math.floor(value / 3600)
    const minutes = Math.round((value % 3600) / 60)
    return hours ? `${hours}h ${minutes}m` : `${minutes}m`
  }

  return (
    <section className="panel intelligence-panel">
      <div className="panel-heading">
        <div><span className="panel-kicker">{t('intelligenceKicker')}</span><h3>{t('intelligenceTitle')}</h3></div>
        <span className="panel-icon"><Brain size={17} /></span>
      </div>
      <div className="intelligence-controls">
        <label className="field">
          <span>{t('intelligencePeriod')}</span>
          <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
            <option value={7}>7 {t('intelligenceDays')}</option>
            <option value={30}>30 {t('intelligenceDays')}</option>
            <option value={90}>90 {t('intelligenceDays')}</option>
            <option value={365}>365 {t('intelligenceDays')}</option>
          </select>
        </label>
      </div>

      {report.isLoading ? <p className="form-note"><LoaderCircle className="spin" size={13} /> {t('loading')}</p>
        : report.isError || !report.data ? <p className="form-error">{t('loadError')}</p>
        : (
          <>
            <p className="panel-note"><Scale size={12} /> {report.data.method.note}</p>

            <h4 className="intelligence-heading"><ShieldCheck size={13} /> {t('intelligenceMeasured')}</h4>
            <div className="intelligence-table-wrap">
              <table className="builder-table intelligence-table">
                <thead>
                  <tr>
                    <th>{t('intelligenceAgent')}</th>
                    <th>{t('intelligenceRole')}</th>
                    <th>{t('intelligenceTasks')}</th>
                    <th>{t('intelligenceSuccess')}</th>
                    <th>{t('intelligenceComplexity')}</th>
                    <th>{t('intelligenceRework')}</th>
                    <th>{t('intelligenceReviews')}</th>
                    <th>{t('intelligenceCompletion')}</th>
                    <th>{t('intelligenceCost')}</th>
                  </tr>
                </thead>
                <tbody>
                  {report.data.agents.filter((agent) => !agent.is_manager).map((agent) => (
                    <tr key={agent.agent_id} className={agent.sample_sufficient ? '' : 'intelligence-thin'}>
                      <td>
                        {agent.name}
                        {!agent.sample_sufficient && <span className="recovery-tag na">{t('intelligenceSmallSample')}</span>}
                      </td>
                      <td>{agent.role}</td>
                      <td>{formatNumber(agent.tasks.total, i18n.language)} <small>({formatNumber(agent.tasks.terminal, i18n.language)} {t('intelligenceTerminal')})</small></td>
                      <td>{pct(agent.success_rate)}</td>
                      <td>{formatNumber(agent.complexity_points, i18n.language)} <small>≈{formatNumber(agent.complexity_points_per_task ?? 0, i18n.language)}/{t('intelligencePerTask')}</small></td>
                      <td>{agent.rework.events} <small>({pct(agent.rework.rate)})</small></td>
                      <td>{agent.reviews.received} <small>({pct(agent.reviews.pass_rate)})</small></td>
                      <td>{secs(agent.completion_time.median_seconds)}</td>
                      <td>{agent.usage.records === 0
                        ? <span className="muted">{t('intelligenceNoCost')}</span>
                        : <>{formatNumber(agent.usage.estimated_cost_usd, i18n.language, { style: 'currency', currency: 'USD', maximumFractionDigits: 4 })} <small>({t('intelligenceEstimate')})</small></>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h4 className="intelligence-heading"><Info size={13} /> {t('intelligenceAssessed')} <span className="recovery-tag manual">{report.data.method.assessment_kind}</span></h4>
            {report.data.assessments.length === 0
              ? <p className="form-note">{t('intelligenceNoAssessments')}</p>
              : (
                <ul className="intelligence-assessments">
                  {report.data.assessments.map((item, index) => (
                    <li key={`${item.topic}-${index}`}>
                      <div className="intelligence-assessment-head">
                        <span className="recovery-tag manual">{item.topic}</span>
                        <strong>{item.subject}</strong>
                        <small>{item.basis.metric}{item.basis.threshold !== undefined ? ` ≥ ${item.basis.threshold}` : ''}</small>
                      </div>
                      <p>{item.finding}</p>
                      <p className="intelligence-recommendation">{item.recommendation}</p>
                      <p className="form-note"><CircleAlert size={11} /> {item.caveat}</p>
                    </li>
                  ))}
                </ul>
              )}
            <p className="form-note">
              {t('intelligenceWeights')}: {Object.entries(report.data.method.complexity_weights).map(([k, v]) => `${k}=${v}`).join(', ')}
              {' · '}{t('intelligenceMinSample')}: {report.data.method.min_sample}
              {' · '}{t('intelligenceNoRanking')}
            </p>
          </>
        )}
    </section>
  )
}
