import { FormEvent, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowRight, Boxes, ClipboardList, FlaskConical, GitBranch, Layers, ListChecks, LoaderCircle, Sparkles, UsersRound } from 'lucide-react'

import { api, BlueprintPlan } from './api'

/**
 * The Project Builder proposes a plan; it never creates anything until the user
 * applies it. Every section shown here comes from the backend's rule engine, and
 * the panel states plainly that no model was called.
 */
export default function ProjectBuilderView() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [plan, setPlan] = useState<BlueprintPlan | null>(null)
  const [confirmed, setConfirmed] = useState(false)

  const generate = useMutation({
    mutationFn: api.buildBlueprint,
    onSuccess: (data) => { setPlan(data); setConfirmed(false) },
  })
  const apply = useMutation({
    mutationFn: (data: BlueprintPlan) => api.applyBlueprint(data),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['projects'] }),
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
      ])
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    generate.mutate({
      idea: String(form.get('idea') ?? '').trim(),
      scale: String(form.get('scale') ?? 'mvp') as BlueprintPlan['options']['scale'],
      stack: String(form.get('stack') ?? 'python-react') as BlueprintPlan['options']['stack'],
      data_layer: String(form.get('data_layer') ?? 'sqlite') as BlueprintPlan['options']['data_layer'],
      team_size: Number(form.get('team_size') ?? 3),
    })
  }

  return (
    <>
      <section className="panel builder-panel">
        <div className="panel-heading">
          <div><span className="panel-kicker">{t('builderKicker')}</span><h3>{t('builderTitle')}</h3></div>
          <span className="panel-icon"><Sparkles size={17} /></span>
        </div>
        <p className="panel-note">{t('builderNote')}</p>
        <form className="form-grid two-columns" onSubmit={submit}>
          <label className="field field-full">
            <span>{t('builderIdea')}</span>
            <textarea name="idea" rows={4} required minLength={20} maxLength={4000} placeholder={t('builderIdeaPlaceholder')} />
          </label>
          <label className="field"><span>{t('builderScale')}</span>
            <select name="scale" defaultValue="mvp">
              <option value="prototype">{t('builderScalePrototype')}</option>
              <option value="mvp">{t('builderScaleMvp')}</option>
              <option value="production">{t('builderScaleProduction')}</option>
            </select>
          </label>
          <label className="field"><span>{t('builderStack')}</span>
            <select name="stack" defaultValue="python-react">
              <option value="python-react">FastAPI + React</option>
              <option value="node-react">Node + React</option>
              <option value="python-only">Python only</option>
            </select>
          </label>
          <label className="field"><span>{t('builderData')}</span>
            <select name="data_layer" defaultValue="sqlite">
              <option value="sqlite">SQLite</option>
              <option value="postgres">PostgreSQL</option>
            </select>
          </label>
          <label className="field"><span>{t('builderTeam')}</span>
            <input name="team_size" type="number" min={1} max={20} defaultValue={3} />
          </label>
          <div className="form-actions field-full">
            <button className="button button-primary" type="submit" disabled={generate.isPending}>
              {generate.isPending ? <><LoaderCircle className="spin" size={14} />{t('builderGenerating')}</> : <>{t('builderGenerate')} <ArrowRight size={13} /></>}
            </button>
          </div>
          {generate.isError && <p className="form-error field-full">{t('requestFailed')}: {generate.error.message}</p>}
        </form>
      </section>

      {plan && (
        <>
          <section className="panel builder-result">
            <div className="panel-heading">
              <div>
                <span className="panel-kicker">{t('builderProposal')} · {plan.fingerprint}</span>
                <h3>{plan.summary.project_name}</h3>
              </div>
              <span className="panel-icon"><Boxes size={17} /></span>
            </div>
            <p className="notice-inline">{t('builderRuleNote')}</p>
            <div className="builder-counts">
              <div><span>{t('builderRequirements')}</span><strong>{plan.summary.requirements}</strong></div>
              <div><span>{t('builderTasks')}</span><strong>{plan.summary.tasks}</strong></div>
              <div><span>{t('builderPhases')}</span><strong>{plan.summary.phases}</strong></div>
              <div><span>{t('builderStaffed')}</span><strong>{plan.summary.staffed_tasks}</strong></div>
              <div><span>{t('builderUnstaffed')}</span><strong>{plan.summary.unstaffed_tasks}</strong></div>
            </div>
          </section>

          <BlueprintSection icon={<ListChecks size={16} />} title={t('builderRequirements')}>
            <ul className="builder-list">
              {plan.requirements.map((item) => (
                <li key={item.id}><strong>{item.id}</strong> {item.text}<span className="builder-source">{item.source}</span></li>
              ))}
            </ul>
          </BlueprintSection>

          <BlueprintSection icon={<Layers size={16} />} title={t('builderArchitecture')}>
            <p>{plan.architecture.shape}</p>
            <ul className="builder-list">{plan.architecture.constraints.map((item) => <li key={item}>{item}</li>)}</ul>
            <p className="form-note">{plan.architecture.data_layer_choice}</p>
          </BlueprintSection>

          <BlueprintSection icon={<Boxes size={16} />} title={t('builderDatabase')}>
            <table className="builder-table">
              <thead><tr><th>{t('builderTable')}</th><th>{t('builderWhy')}</th></tr></thead>
              <tbody>
                {plan.database_design.map((table) => (
                  <tr key={table.table}><td>{table.table}</td><td>{table.why}</td></tr>
                ))}
              </tbody>
            </table>
          </BlueprintSection>

          <BlueprintSection icon={<ClipboardList size={16} />} title={t('builderPhases')}>
            <ol className="builder-phases">
              {plan.development_phases.map((phase) => (
                <li key={phase.name}><strong>{phase.name}</strong><span>{phase.tasks.length} {t('builderTasksLower')}</span><p>{phase.exit_criteria}</p></li>
              ))}
            </ol>
          </BlueprintSection>

          <BlueprintSection icon={<GitBranch size={16} />} title={t('builderTaskBreakdown')}>
            <table className="builder-table">
              <thead><tr><th>#</th><th>{t('builderTask')}</th><th>{t('builderRole')}</th><th>{t('builderDependsOn')}</th></tr></thead>
              <tbody>
                {plan.task_breakdown.map((task) => (
                  <tr key={task.key}>
                    <td>{task.order}</td>
                    <td>{task.title}</td>
                    <td>{task.role}</td>
                    <td>{task.depends_on.length ? task.depends_on.join(', ') : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </BlueprintSection>

          <BlueprintSection icon={<UsersRound size={16} />} title={t('builderAssignments')}>
            <ul className="builder-list">
              {plan.assignment_plan.map((item) => (
                <li key={item.task_key}>
                  <strong>{item.task_key}</strong> {item.agent_name ?? t('builderNoWorker')}
                  <span className="builder-source">{item.reason}</span>
                </li>
              ))}
            </ul>
          </BlueprintSection>

          <BlueprintSection icon={<FlaskConical size={16} />} title={t('builderTesting')}>
            <ul className="builder-list">{plan.testing_strategy.map((item) => <li key={item}>{item}</li>)}</ul>
          </BlueprintSection>

          <BlueprintSection icon={<ListChecks size={16} />} title={t('builderAcceptance')}>
            <ul className="builder-list">{plan.acceptance_criteria.map((item) => <li key={item}>{item}</li>)}</ul>
          </BlueprintSection>

          <BlueprintSection icon={<ArrowRight size={16} />} title={t('builderDelivery')}>
            <table className="builder-table">
              <thead><tr><th>{t('builderMilestone')}</th><th>{t('builderExit')}</th><th>{t('builderGate')}</th></tr></thead>
              <tbody>
                {plan.delivery_plan.map((item) => (
                  <tr key={item.milestone}><td>{item.milestone}</td><td>{item.exit_criteria}</td><td>{item.gate}</td></tr>
                ))}
              </tbody>
            </table>
          </BlueprintSection>

          <section className="panel builder-apply">
            <div className="panel-heading"><div><span className="panel-kicker">{t('builderApplyKicker')}</span><h3>{t('builderApplyTitle')}</h3></div></div>
            <p className="panel-note">{t('builderApplyNote')}</p>
            <label className="check-row">
              <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
              <span>{t('builderConfirm')}</span>
            </label>
            <div className="form-actions">
              <button
                className="button button-primary"
                type="button"
                disabled={!confirmed || apply.isPending}
                onClick={() => apply.mutate(plan)}
              >
                {apply.isPending ? t('builderApplying') : t('builderApply')}
              </button>
            </div>
            {apply.isSuccess && (
              <p className="form-success">{t('builderApplied')}: {apply.data.tasks_created} {t('builderTasksLower')}, {apply.data.project_name}</p>
            )}
            {apply.isError && <p className="form-error">{t('requestFailed')}: {apply.error.message}</p>}
          </section>
        </>
      )}
    </>
  )
}

function BlueprintSection({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <section className="panel builder-section">
      <div className="panel-heading"><div><h3>{title}</h3></div><span className="panel-icon">{icon}</span></div>
      {children}
    </section>
  )
}
