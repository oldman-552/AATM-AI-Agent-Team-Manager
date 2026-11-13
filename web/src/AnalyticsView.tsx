import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Activity, BarChart3, ClipboardCheck, GitPullRequest, RotateCcw } from 'lucide-react'

import { api } from './api'
import IntelligencePanel from './IntelligencePanel'

function formatDuration(seconds: number | null, t: (key: string) => string): string {
  if (seconds === null) return '—'
  if (seconds < 60) return `${Math.round(seconds)} ${t('analyticsSeconds')}`
  if (seconds < 3600) return `${Math.round(seconds / 60)} ${t('analyticsMinutes')}`
  return `${(seconds / 3600).toFixed(1)} ${t('analyticsHours')}`
}

export default function AnalyticsView() {
  const { t } = useTranslation()
  const overview = useQuery({ queryKey: ['analytics'], queryFn: () => api.analytics(14) })

  if (overview.isLoading) return <section className="panel"><p className="form-note">{t('loading')}</p></section>
  if (overview.isError || !overview.data) {
    return <section className="panel"><p className="form-error">{t('requestFailed')}: {overview.error?.message ?? ''}</p></section>
  }
  const data = overview.data
  const peakThroughput = Math.max(1, ...data.throughput.buckets.map((bucket) => bucket.completed + bucket.approved))
  const peakActivity = Math.max(1, ...data.activity.buckets.map((bucket) => bucket.events))

  return (
    <>
      <section className="view-header">
        <div>
          <span className="eyebrow"><BarChart3 size={12} /> {t('analyticsEyebrow')}</span>
          <h2>{t('analyticsTitle')}</h2>
          <p>{t('analyticsSubtitle')}</p>
        </div>
      </section>

      <section className="metric-grid">
        <article className="metric-card"><span>{t('analyticsProjects')}</span><strong>{data.counts.projects}</strong></article>
        <article className="metric-card"><span>{t('analyticsAgents')}</span><strong>{data.counts.agents}</strong></article>
        <article className="metric-card"><span>{t('analyticsActiveTasks')}</span><strong>{data.counts.tasks_active}</strong></article>
        <article className="metric-card"><span>{t('analyticsTerminalTasks')}</span><strong>{data.counts.tasks_terminal}</strong></article>
        <article className="metric-card"><span>{t('analyticsCheckpoints')}</span><strong>{data.counts.checkpoints}</strong></article>
      </section>

      <section className="panel">
        <div className="panel-header"><div><span className="panel-kicker"><Activity size={12} /> {t('analyticsThroughput')}</span><h3>{t('analyticsThroughputTitle')}</h3></div></div>
        <div className="bar-chart" role="img" aria-label={t('analyticsThroughputTitle')}>
          {data.throughput.buckets.map((bucket) => {
            const value = bucket.completed + bucket.approved
            return (
              <div className="bar-chart-column" key={bucket.date}>
                <span className="bar-chart-value">{value}</span>
                <div className="bar-chart-bar" style={{ height: `${Math.max(3, (value / peakThroughput) * 100)}%` }} title={`${bucket.date}: ${value}`} />
                <span className="bar-chart-label">{bucket.date.slice(5)}</span>
              </div>
            )
          })}
        </div>
        <p className="form-note">{data.throughput.source} · {t('analyticsTotal')}: {data.throughput.total}</p>
      </section>

      <section className="panel">
        <div className="panel-header"><div><span className="panel-kicker"><Activity size={12} /> {t('analyticsActivity')}</span><h3>{t('analyticsActivityTitle')}</h3></div></div>
        <div className="bar-chart" role="img" aria-label={t('analyticsActivityTitle')}>
          {data.activity.buckets.map((bucket) => (
            <div className="bar-chart-column" key={bucket.date}>
              <span className="bar-chart-value">{bucket.events}</span>
              <div className="bar-chart-bar secondary" style={{ height: `${Math.max(3, (bucket.events / peakActivity) * 100)}%` }} title={`${bucket.date}: ${bucket.events}`} />
              <span className="bar-chart-label">{bucket.date.slice(5)}</span>
            </div>
          ))}
        </div>
        <p className="form-note">{data.activity.source} · {t('analyticsTotal')}: {data.activity.total}</p>
      </section>

      <section className="metric-grid">
        <article className="metric-card">
          <span><ClipboardCheck size={12} /> {t('analyticsCycleTime')}</span>
          <strong>{formatDuration(data.cycle_time.median_seconds, t)}</strong>
          <p className="form-note">{t('analyticsSamples')}: {data.cycle_time.samples}</p>
        </article>
        <article className="metric-card">
          <span><ClipboardCheck size={12} /> {t('analyticsApprovalRate')}</span>
          <strong>{data.reviews.approval_rate === null ? '—' : `${Math.round(data.reviews.approval_rate * 100)}%`}</strong>
          <p className="form-note">{t('analyticsReviews')}: {data.reviews.total}</p>
        </article>
        <article className="metric-card">
          <span><RotateCcw size={12} /> {t('analyticsRework')}</span>
          <strong>{data.rework.share === null ? '—' : `${Math.round(data.rework.share * 100)}%`}</strong>
          <p className="form-note">{t('analyticsReworkTasks')}: {data.rework.tasks_with_rework}</p>
        </article>
        <article className="metric-card">
          <span><GitPullRequest size={12} /> {t('analyticsPendingApprovals')}</span>
          <strong>{data.approvals.pending}</strong>
          <p className="form-note">{data.approvals.source}</p>
        </article>
      </section>

      <section className="panel">
        <div className="panel-header"><div><span className="panel-kicker">{t('analyticsNotes')}</span></div></div>
        <ul className="analytics-notes">{data.notes.map((note: string) => <li key={note}>{note}</li>)}</ul>
      </section>

      <IntelligencePanel />
    </>
  )
}
