import { FormEvent, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { GitPullRequest, Lock } from 'lucide-react'

import { api, PullRequestPlan } from '../api'

/**
 * Pull-request plans.
 *
 * The UI never offers a "create PR" button that would imply network access:
 * it records a plan, shows the exact commands a future executor would run,
 * and asks for an explicit approval decision.
 */
export function PullRequestPlans({ projectId }: { projectId: string }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [formOpen, setFormOpen] = useState(false)
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [base, setBase] = useState('main')
  const [head, setHead] = useState('')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [decidedBy, setDecidedBy] = useState('local-user')

  const plans = useQuery({
    queryKey: ['pullRequests', projectId],
    queryFn: () => api.pullRequestPlans(projectId),
    enabled: Boolean(projectId),
  })
  const create = useMutation({
    mutationFn: () =>
      api.createPullRequestPlan(projectId, {
        owner, repo, base_branch: base, head_branch: head, title, body,
      }),
    onSuccess: async () => {
      setFormOpen(false)
      setOwner('')
      setRepo('')
      setHead('')
      setTitle('')
      setBody('')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['pullRequests', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['approvals'] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
      ])
    },
  })
  const decide = useMutation({
    mutationFn: ({ plan, status }: { plan: PullRequestPlan; status: 'approved' | 'rejected' }) =>
      api.decidePullRequestPlan(projectId, plan.id, { status, decided_by: decidedBy }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['pullRequests', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['approvals'] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
      ])
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate()
  }

  return (
    <div className="pr-plans">
      <div className="pr-plans-header">
        <span className="panel-kicker"><GitPullRequest size={12} /> {t('pullRequestsTitle')}</span>
        <button className="button button-secondary" type="button" onClick={() => setFormOpen((value) => !value)}>
          {formOpen ? t('cancel') : t('pullRequestPlanNew')}
        </button>
      </div>
      <p className="form-note"><Lock size={11} /> {t('pullRequestNoNetworkNote')}</p>

      {formOpen && (
        <form className="pr-plan-form" onSubmit={submit}>
          <label><span>{t('pullRequestOwner')}</span><input value={owner} maxLength={39} required onChange={(event) => setOwner(event.target.value)} /></label>
          <label><span>{t('pullRequestRepo')}</span><input value={repo} maxLength={100} required onChange={(event) => setRepo(event.target.value)} /></label>
          <label><span>{t('pullRequestBase')}</span><input value={base} maxLength={121} required onChange={(event) => setBase(event.target.value)} /></label>
          <label><span>{t('pullRequestHead')}</span><input value={head} maxLength={121} required onChange={(event) => setHead(event.target.value)} /></label>
          <label className="pr-plan-wide"><span>{t('pullRequestPlanTitle')}</span><input value={title} maxLength={200} required onChange={(event) => setTitle(event.target.value)} /></label>
          <label className="pr-plan-wide"><span>{t('pullRequestBody')}</span><textarea value={body} maxLength={20000} rows={3} onChange={(event) => setBody(event.target.value)} /></label>
          <div className="pr-plan-wide pr-plan-actions">
            <button className="button button-primary" type="submit" disabled={create.isPending}>{t('pullRequestPlanCreate')}</button>
            {create.isError && <p className="form-error">{t('requestFailed')}: {create.error.message}</p>}
          </div>
        </form>
      )}

      {plans.data?.plans.length ? (
        <div className="pr-plan-list">
          {plans.data.plans.map((plan) => (
            <article className="pr-plan-card" key={plan.id}>
              <div className="pr-plan-top">
                <strong>{plan.repository}</strong>
                <span className={`status-chip ${plan.status === 'rejected' ? 'offline' : ''}`}>{plan.status === 'awaiting_approval' ? t('pullRequestAwaiting') : plan.status === 'rejected' ? t('pullRequestRejected') : t('pullRequestApprovedNotExecuted')}</span>
              </div>
              <p className="pr-plan-branch">{plan.head_branch} → {plan.base_branch}</p>
              <h4>{plan.title}</h4>
              {plan.body && <p className="pr-plan-body">{plan.body}</p>}
              <details className="pr-plan-commands">
                <summary>{t('pullRequestPlannedCommands')}</summary>
                <pre>{plan.commands.join('\n')}</pre>
              </details>
              <p className="form-note">{plan.execution_reason}</p>
              {plan.status === 'awaiting_approval' && (
                <div className="pr-plan-actions">
                  <label><span>{t('pullRequestDecidedBy')}</span><input value={decidedBy} maxLength={120} onChange={(event) => setDecidedBy(event.target.value)} /></label>
                  <button className="button button-secondary" type="button" disabled={decide.isPending} onClick={() => decide.mutate({ plan, status: 'approved' })}>{t('approvalApprove')}</button>
                  <button className="button button-secondary" type="button" disabled={decide.isPending} onClick={() => decide.mutate({ plan, status: 'rejected' })}>{t('approvalReject')}</button>
                </div>
              )}
              {decide.isError && <p className="form-error">{t('requestFailed')}: {decide.error.message}</p>}
            </article>
          ))}
        </div>
      ) : (
        <p className="form-note">{t('pullRequestEmpty')}</p>
      )}
    </div>
  )
}
