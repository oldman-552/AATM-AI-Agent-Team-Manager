import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowRight, CheckCircle2, CircleSlash, History, LoaderCircle, ShieldQuestion } from 'lucide-react'

import { api, TimelineEntry } from './api'
import { formatDateTime } from './format'

/**
 * The timeline is a projection of stored rows. Every row shown here exists in the
 * database, and its `source` table is displayed so a reader can audit it. Nothing
 * is inferred, and no future event is predicted.
 */
export default function TaskTimelineView({ taskId, language }: { taskId: string; language: string }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const timeline = useQuery({
    queryKey: ['taskTimeline', taskId],
    queryFn: () => api.taskTimeline(taskId),
    enabled: open,
  })

  const detail = (entry: TimelineEntry): string | null => entry.detail?.trim() ? entry.detail : null

  const badge = (entry: TimelineEntry) => {
    if (entry.kind === 'transition') return `${String(entry.data.from ?? '')} → ${String(entry.data.to ?? '')}`
    if (entry.kind === 'checkpoint') return `${t('timelineCheckpoint')} #${String(entry.data.sequence ?? '?')}`
    if (entry.kind === 'review') return String(entry.data.verdict ?? t('timelineReview'))
    if (entry.kind === 'approval') return String(entry.data.decision ?? entry.data.status ?? t('timelineApproval'))
    return String(entry.data.event_type ?? t('timelineAudit'))
  }

  return (
    <div className="timeline-block">
      <button className="button button-quiet" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <History size={14} />{open ? t('timelineHide') : t('timelineShow')}
      </button>
      {open && (
        timeline.isLoading ? <p className="form-note"><LoaderCircle className="spin" size={13} /> {t('loading')}</p>
          : timeline.isError ? <p className="form-error">{t('loadError')}</p>
          : timeline.data ? (
            <>
              <p className="timeline-note">{t('timelineNote')}</p>
              {timeline.data.entries.length ? (
                <ol className="timeline-list">
                  {timeline.data.entries.map((entry) => (
                    <li key={`${entry.source}-${entry.reference}`} className={`timeline-entry ${entry.kind}`}>
                      <span className="timeline-dot" aria-hidden="true" />
                      <div className="timeline-body">
                        <div className="timeline-head">
                          <strong>{badge(entry)}</strong>
                          <time>{formatDateTime(entry.at, language)}</time>
                        </div>
                        {detail(entry) && <p>{detail(entry)}</p>}
                        <span className="timeline-source">{t('timelineSource')}: {entry.source}</span>
                      </div>
                    </li>
                  ))}
                </ol>
              ) : <p className="form-note">{t('timelineEmpty')}</p>}
              <p className="timeline-footnote">
                {t('timelineCount')}: {timeline.data.total} · {t('timelineSources')}: {timeline.data.sources.join(', ') || t('timelineNoSources')}
                {timeline.data.truncated ? ` · ${t('timelineTruncated')}` : ''}
              </p>
            </>
          ) : null
        )}
    </div>
  )
}

/** Request, withdraw, or apply a cancellation. Always asks for a reason first. */
export function CancelControls({ task }: { task: { id: string; state: string; cancel_requested_at?: string | null; cancel_reason?: string | null } }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['tasks'] }),
      queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      queryClient.invalidateQueries({ queryKey: ['readyTasks'] }),
      queryClient.invalidateQueries({ queryKey: ['taskTimeline', task.id] }),
      queryClient.invalidateQueries({ queryKey: ['events'] }),
    ])
  }
  const request = useMutation({
    mutationFn: (value: string) => api.requestCancel(task.id, value),
    onSuccess: async () => { setOpen(false); setReason(''); await refresh() },
  })
  const withdraw = useMutation({ mutationFn: () => api.withdrawCancel(task.id), onSuccess: refresh })
  const apply = useMutation({ mutationFn: () => api.applyCancel(task.id), onSuccess: refresh })

  const finished = task.state === 'completed' || task.state === 'approved' || task.state === 'cancelled'
  const pending = Boolean(task.cancel_requested_at)

  if (pending) {
    return (
      <div className="cancel-block pending">
        <p className="cancel-banner"><ShieldQuestion size={14} />{t('cancelPending')} <span>{task.cancel_reason}</span></p>
        <div className="cancel-actions">
          <button className="button button-secondary" type="button" disabled={apply.isPending} onClick={() => apply.mutate()}>
            {apply.isPending ? t('cancelApplying') : t('cancelApplyNow')}
          </button>
          <button className="button button-quiet" type="button" disabled={withdraw.isPending} onClick={() => withdraw.mutate()}>
            {t('cancelWithdraw')}
          </button>
        </div>
        {apply.isSuccess && <p className="form-success"><CheckCircle2 size={13} />{apply.data.cancelled ? t('cancelApplied') : t('cancelTooLate')}</p>}
        {(apply.isError || withdraw.isError) && <p className="form-error">{t('requestFailed')}</p>}
      </div>
    )
  }

  if (finished) return null

  return (
    <div className="cancel-block">
      <button className="button button-quiet" type="button" onClick={() => setOpen((value) => !value)}>
        <CircleSlash size={14} />{t('cancelRequest')}
      </button>
      {open && (
        <div className="cancel-form">
          <label className="field">
            <span>{t('cancelReason')}</span>
            <input value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} placeholder={t('cancelReasonPlaceholder')} />
          </label>
          <p className="form-note">{t('cancelExplainer')}</p>
          <div className="form-actions">
            <button className="button button-secondary" type="button" onClick={() => setOpen(false)}>{t('cancel')}</button>
            <button
              className="button button-danger"
              type="button"
              disabled={request.isPending || !reason.trim()}
              onClick={() => request.mutate(reason.trim())}
            >
              {request.isPending ? t('cancelSubmitting') : t('cancelConfirm')} <ArrowRight size={12} />
            </button>
          </div>
          {request.isError && <p className="form-error">{t('requestFailed')}: {request.error.message}</p>}
        </div>
      )}
    </div>
  )
}
