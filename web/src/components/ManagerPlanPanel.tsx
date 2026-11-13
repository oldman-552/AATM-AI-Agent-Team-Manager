import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ClipboardList, Play, RefreshCw } from 'lucide-react'

import { api } from '../api'

/**
 * Manager proposals are deterministic rules over stored rows. They are shown
 * for review and applied only when the operator explicitly asks, and each
 * proposal is re-validated server-side at apply time.
 */
export function ManagerPlanPanel({ projectId }: { projectId?: string }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const plan = useQuery({
    queryKey: ['managerPlan', projectId ?? 'all'],
    queryFn: () => api.managerPlan(projectId),
  })
  const apply = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.applyManagerPlan(payload, 'manager'),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['managerPlan'] }),
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
        queryClient.invalidateQueries({ queryKey: ['notifications'] }),
      ])
    },
  })

  if (plan.isLoading || !plan.data) return null
  const data = plan.data
  const severityKey: Record<string, string> = { error: 'planSeverityError', warning: 'planSeverityWarning', info: 'planSeverityInfo' }

  return (
    <section className="panel manager-plan">
      <div className="panel-header">
        <div>
          <span className="panel-kicker"><ClipboardList size={12} /> {t('planKicker')}</span>
          <h3>{t('planTitle')}</h3>
        </div>
        <div className="heading-actions">
          <button className="button button-secondary" type="button" onClick={() => plan.refetch()} disabled={plan.isFetching}>
            <RefreshCw size={12} /> {t('planRefresh')}
          </button>
          <button
            className="button button-primary"
            type="button"
            disabled={apply.isPending || data.proposals.length === 0}
            onClick={() => apply.mutate(data as unknown as Record<string, unknown>)}
          >
            <Play size={12} /> {t('planApply')}
          </button>
        </div>
      </div>
      <p className="form-note">{t('planNote')}</p>

      {data.findings.length > 0 && (
        <ul className="plan-findings">
          {data.findings.map((finding, index) => (
            <li key={`${finding.code}-${index}`} className={`plan-finding ${finding.severity}`}>
              <span className="plan-severity">{t(severityKey[finding.severity] ?? 'planSeverityInfo')}</span>
              <span>{t(`planFinding_${finding.code}`, { ...finding })}</span>
            </li>
          ))}
        </ul>
      )}

      {data.proposals.length === 0 ? (
        <p className="form-note">{t('planNoProposals')}</p>
      ) : (
        <ul className="plan-proposals">
          {data.proposals.map((proposal) => (
            <li key={proposal.task_id}>
              <span>{proposal.task_title}</span>
              <span className="plan-arrow">→</span>
              <code>{proposal.suggested_agent_id}</code>
              <span className="plan-reason">{t('planAssignLeastLoaded')}</span>
            </li>
          ))}
        </ul>
      )}

      {apply.isSuccess && (
        <p className="form-success">
          {t('planApplied', { applied: apply.data.applied.length, skipped: apply.data.skipped.length })}
        </p>
      )}
      {apply.isError && <p className="form-error">{t('requestFailed')}: {apply.error.message}</p>}
      <p className="form-note">{data.planner}</p>
    </section>
  )
}
