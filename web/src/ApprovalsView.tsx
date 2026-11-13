import { FormEvent, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, CircleAlert, LoaderCircle, Plus, ShieldCheck, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDateTime } from './format'
import { api, type Approval } from './api'

const kinds = [
  { id: 'paid_provider_request', label: 'approvalKindPaidProvider' },
  { id: 'protected_branch_merge', label: 'approvalKindMerge' },
  { id: 'deployment', label: 'approvalKindDeployment' },
  { id: 'data_deletion', label: 'approvalKindDeletion' },
] as const

const kindLabels: Record<string, string> = Object.fromEntries(kinds.map((kind) => [kind.id, kind.label]))

export default function ApprovalsView() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const approvals = useQuery({ queryKey: ['approvals'], queryFn: api.approvals })
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<string>(kinds[0].id)
  const [summary, setSummary] = useState('')
  const [decider, setDecider] = useState('local-user')

  const create = useMutation({
    mutationFn: api.createApproval,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['approvals'] })
      setSummary('')
      setOpen(false)
    },
  })
  const decide = useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'approved' | 'rejected' }) =>
      api.decideApproval(id, { status, decided_by: decider, note: '' }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['approvals'] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
      ])
    },
  })

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    create.mutate({ kind, entity_type: 'task', entity_id: null, summary: summary.trim() })
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> AATM <span> / </span> {t('approvalsTitle')}</div>
          <h1>{t('approvalsTitle')}</h1>
          <p>{t('approvalsSubtitle')}</p>
        </div>
        <button className="button button-primary" type="button" onClick={() => setOpen((value) => !value)}>
          <Plus size={16} />{t('approvalRequest')}
        </button>
      </div>

      {open && (
        <section className="panel approval-form-panel">
          <form className="form-grid two-columns" onSubmit={submit}>
            <label className="field">
              <span>{t('approvalKind')}</span>
              <select value={kind} onChange={(event) => setKind(event.target.value)}>
                {kinds.map((item) => <option key={item.id} value={item.id}>{t(item.label)}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t('approvalDecideBy')}</span>
              <input value={decider} maxLength={120} onChange={(event) => setDecider(event.target.value)} />
            </label>
            <label className="field field-full">
              <span>{t('approvalSummary')}</span>
              <textarea rows={3} maxLength={500} required value={summary} onChange={(event) => setSummary(event.target.value)} />
            </label>
            {create.isError && <p className="form-error field-full">{t('requestFailed')}: {create.error.message}</p>}
            <div className="form-actions field-full">
              <button className="button button-secondary" type="button" onClick={() => setOpen(false)}>{t('cancel')}</button>
              <button className="button button-primary" type="submit" disabled={create.isPending || !summary.trim()}>{t('approvalRequest')}</button>
            </div>
          </form>
        </section>
      )}

      {create.isSuccess && <div className="notice-panel"><Check size={17} /><p>{t('approvalCreated')}</p></div>}

      {approvals.isLoading ? (
        <div className="state-panel"><span><LoaderCircle className="spin" size={22} /></span><p>{t('loading')}</p></div>
      ) : approvals.isError || !approvals.data ? (
        <div className="state-panel"><span><CircleAlert size={22} /></span><p>{t('loadError')}</p></div>
      ) : approvals.data.approvals.length ? (
        <div className="approval-list">
          {approvals.data.approvals.map((approval) => (
            <ApprovalRow key={approval.id} approval={approval} onDecide={(status) => decide.mutate({ id: approval.id, status })} pending={decide.isPending} />
          ))}
        </div>
      ) : (
        <div className="state-panel"><span><ShieldCheck size={22} /></span><p>{t('approvalsEmpty')}</p></div>
      )}
      <p className="form-note approval-footnote">{t('approvalDecided')}</p>
    </>
  )
}

function ApprovalRow({ approval, onDecide, pending }: { approval: Approval; onDecide: (status: 'approved' | 'rejected') => void; pending: boolean }) {
  const { t } = useTranslation()
  const { i18n } = useTranslation()
  return (
    <article className="panel approval-row">
      <div className="approval-row-main">
        <span className="panel-kicker">{t(kindLabels[approval.kind] ?? approval.kind)}</span>
        <h3>{approval.summary}</h3>
        <div className="approval-row-meta">
          <span>{formatDateTime(approval.requested_at, i18n.language)}</span>
          {approval.decided_by && <span>{t('approvalDecideBy')}: {approval.decided_by}</span>}
        </div>
      </div>
      <span className={`status-chip approval-status-${approval.status}`}>
        {approval.status === 'pending' ? t('approvalPending') : approval.status === 'approved' ? t('approvalApproved') : t('approvalRejected')}
      </span>
      {approval.status === 'pending' && (
        <div className="approval-actions">
          <button className="button button-secondary task-action-button" type="button" disabled={pending} onClick={() => onDecide('approved')}><Check size={12} />{t('approvalApprove')}</button>
          <button className="button button-secondary task-action-button" type="button" disabled={pending} onClick={() => onDecide('rejected')}><X size={12} />{t('approvalReject')}</button>
        </div>
      )}
    </article>
  )
}
