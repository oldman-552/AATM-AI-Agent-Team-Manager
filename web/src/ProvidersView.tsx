import { FormEvent, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Ban, Check, CircleAlert, LoaderCircle, PlugZap, Route, Send, ShieldCheck, Wallet } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  api,
  type ProviderDescriptor,
  type ProviderState,
  type RouteDecision,
  type RoutingPolicy,
  type TaskComplexity,
} from './api'

const policies: RoutingPolicy[] = ['arena_first', 'claude_first', 'manual', 'task_based', 'user_defined']
const complexities: TaskComplexity[] = ['low', 'medium', 'high']

const policyTranslationKey: Record<RoutingPolicy, string> = {
  arena_first: 'routingPolicyArenaFirst',
  claude_first: 'routingPolicyClaudeFirst',
  manual: 'routingPolicyManual',
  task_based: 'routingPolicyTaskBased',
  user_defined: 'routingPolicyUserDefined',
}

const stateTranslationKey: Record<ProviderState, string> = {
  offline_ready: 'providerOfflineReady',
  unconfigured: 'providerUnconfigured',
  disabled: 'providerDisabled',
  blocked: 'providerBlocked',
  budget_exhausted: 'providerBudgetExhausted',
  not_permitted: 'providerNotPermitted',
}

const scopeTranslationKey: Record<string, string> = {
  daily: 'budgetScopeDaily',
  monthly: 'budgetScopeMonthly',
  agent: 'budgetScopeAgent',
  project: 'budgetScopeProject',
  credential: 'budgetScopeCredential',
  global: 'budgetScopeGlobal',
}

function money(value: number, language: string): string {
  return new Intl.NumberFormat(language, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(value)
}

export default function ProvidersView() {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const catalog = useQuery({ queryKey: ['providers'], queryFn: api.providers })
  const budgets = useQuery({ queryKey: ['budgets'], queryFn: api.budgets })
  const [policy, setPolicy] = useState<RoutingPolicy | ''>('')
  const [complexity, setComplexity] = useState<TaskComplexity>('medium')
  const [paidConsent, setPaidConsent] = useState(false)
  const [inputTokens, setInputTokens] = useState('1000')
  const [outputTokens, setOutputTokens] = useState('1024')
  const [budgetValue, setBudgetValue] = useState('0.50')

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['providers'] }),
      queryClient.invalidateQueries({ queryKey: ['budgets'] }),
    ])
  }

  const routeMutation = useMutation({ mutationFn: api.routeDryRun })
  const settingsMutation = useMutation({
    mutationFn: api.updateProviderSettings,
    onSuccess: invalidate,
  })
  const budgetMutation = useMutation({ mutationFn: api.setBudget, onSuccess: invalidate })

  const effectivePolicy = policy || catalog.data?.settings.routing_policy || 'arena_first'
  const submitRoute = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    routeMutation.mutate({
      policy: effectivePolicy,
      complexity,
      paid_consent: paidConsent,
      estimated_input_tokens: Number(inputTokens) || 0,
      estimated_output_tokens: Number(outputTokens) || 0,
    })
  }

  const submitBudget = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    budgetMutation.mutate({
      scope: 'daily',
      provider_id: 'anthropic',
      limit_usd: Math.max(0, Number(budgetValue) || 0),
    })
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> AATM <span> / </span> {t('providersTitle')}</div>
          <h1>{t('providersTitle')}</h1>
          <p>{t('providersSubtitle')}</p>
        </div>
        <span className="live-pill"><ShieldCheck size={13} />{t('providerLiveCallsOff')}</span>
      </div>

      <div className="notice-panel">
        <PlugZap size={17} />
        <p>{t('providerOfflineNote')}</p>
      </div>

      {catalog.isLoading ? (
        <div className="state-panel"><span><LoaderCircle className="spin" size={22} /></span><p>{t('loading')}</p></div>
      ) : catalog.isError || !catalog.data ? (
        <div className="state-panel"><span><CircleAlert size={22} /></span><p>{t('loadError')}</p></div>
      ) : (
        <>
          <div className="provider-grid">
            {catalog.data.providers.map((provider) => (
              <ProviderCard key={provider.id} provider={provider} />
            ))}
          </div>

          <div className="content-grid provider-panels">
            <section className="panel route-panel">
              <div className="panel-heading">
                <div><span className="panel-kicker">{t('providerLiveCallsOff')}</span><h3>{t('routingTitle')}</h3></div>
                <span className="panel-icon"><Route size={17} /></span>
              </div>
              <p className="panel-note">{t('routingSubtitle')}</p>
              <form className="route-form" onSubmit={submitRoute}>
                <label className="field">
                  <span>{t('routingPolicy')}</span>
                  <select value={effectivePolicy} onChange={(event) => setPolicy(event.target.value as RoutingPolicy)}>
                    {policies.map((item) => <option key={item} value={item}>{t(policyTranslationKey[item])}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>{t('routingComplexity')}</span>
                  <select value={complexity} onChange={(event) => setComplexity(event.target.value as TaskComplexity)}>
                    {complexities.map((item) => <option key={item} value={item}>{t(`complexity${item[0].toUpperCase()}${item.slice(1)}`)}</option>)}
                  </select>
                </label>
                <label className="field"><span>{t('routingInputTokens')}</span><input type="number" min="0" max="1000000" value={inputTokens} onChange={(event) => setInputTokens(event.target.value)} /></label>
                <label className="field"><span>{t('routingOutputTokens')}</span><input type="number" min="0" max="1000000" value={outputTokens} onChange={(event) => setOutputTokens(event.target.value)} /></label>
                <label className="checkbox-field field-full">
                  <input type="checkbox" checked={paidConsent} onChange={(event) => setPaidConsent(event.target.checked)} />
                  <span>{t('routingPaidConsent')}</span>
                </label>
                <div className="form-actions field-full">
                  <button className="button button-secondary" type="button" disabled={settingsMutation.isPending} onClick={() => settingsMutation.mutate({ routing_policy: effectivePolicy })}>
                    {t('settingsSaveDefault')}
                  </button>
                  <button className="button button-primary" type="submit" disabled={routeMutation.isPending}>
                    <Send size={14} />{routeMutation.isPending ? t('routingRunning') : t('routingRun')}
                  </button>
                </div>
                {settingsMutation.isSuccess && <p className="form-success field-full"><Check size={13} />{t('settingsUpdated')}</p>}
                {routeMutation.isError && <p className="form-error field-full">{t('requestFailed')}: {routeMutation.error.message}</p>}
              </form>
              {routeMutation.data && <RouteResult decision={routeMutation.data} />}
            </section>

            <section className="panel budget-panel">
              <div className="panel-heading">
                <div><span className="panel-kicker">{t('providerCompliance')}</span><h3>{t('budgetsTitle')}</h3></div>
                <span className="panel-icon"><Wallet size={17} /></span>
              </div>
              <p className="panel-note">{t('budgetsSubtitle')}</p>
              <div className="inline-list">
                {catalog.data.budget_limits.length ? catalog.data.budget_limits.map((limit) => (
                  <div className="inline-row" key={`${limit.scope}-${limit.provider_id}-${limit.scope_key ?? ''}`}>
                    <span>{t(scopeTranslationKey[limit.scope] ?? limit.scope)} · {limit.provider_id}</span>
                    <strong>{money(limit.limit_usd, i18n.language)}</strong>
                  </div>
                )) : <p className="empty-inline">{t('budgetNoLimits')}</p>}
              </div>
              <form className="route-form compact" onSubmit={submitBudget}>
                <label className="field"><span>{t('budgetSetLimit')}</span><input type="number" min="0" step="0.01" value={budgetValue} onChange={(event) => setBudgetValue(event.target.value)} /></label>
                <div className="form-actions"><button className="button button-primary" type="submit" disabled={budgetMutation.isPending}>{t('budgetSave')}</button></div>
                {budgetMutation.isSuccess && <p className="form-success"><Check size={13} />{t('budgetUpdated')}</p>}
                {budgetMutation.isError && <p className="form-error">{t('requestFailed')}: {budgetMutation.error.message}</p>}
              </form>
              <div className="system-divider" />
              <div className="inline-list">
                <div className="inline-row"><span>{t('budgetUsageRecords')}</span><strong>{budgets.data?.usage.total_records ?? 0}</strong></div>
                {Object.entries(budgets.data?.usage.by_provider ?? {}).map(([providerId, totals]) => (
                  <div className="inline-row" key={providerId}>
                    <span>{providerId} · {t('budgetEstimatedTotal')}</span>
                    <strong>{money(totals.estimated_cost_usd, i18n.language)}</strong>
                  </div>
                ))}
                {catalog.data.pricing.basis && <p className="form-note">{catalog.data.pricing.basis}</p>}
              </div>
            </section>
          </div>
        </>
      )}
    </>
  )
}

function ProviderCard({ provider }: { provider: ProviderDescriptor }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [model, setModel] = useState(provider.config.model ?? '')
  const [credential, setCredential] = useState(provider.config.credential?.reference ?? '')
  const [enabled, setEnabled] = useState(provider.config.enabled)
  const mutation = useMutation({
    mutationFn: (payload: { enabled: boolean; model?: string; credential_ref?: string; clear_credential?: boolean }) =>
      api.updateProviderConfig(provider.id, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['providers'] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
      ])
    },
  })

  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const payload: { enabled: boolean; model?: string; credential_ref?: string; clear_credential?: boolean } = { enabled }
    if (model.trim()) payload.model = model.trim()
    if (credential.trim()) payload.credential_ref = credential.trim()
    else if (provider.config.credential) payload.clear_credential = true
    mutation.mutate(payload)
  }

  const isBlocked = provider.health.state === 'blocked'
  return (
    <article className={`record-card provider-card ${isBlocked ? 'provider-blocked' : ''}`}>
      <div className="record-card-top">
        <span className={`record-icon ${isBlocked ? 'amber' : 'violet'}`}>{isBlocked ? <Ban size={18} /> : <PlugZap size={18} />}</span>
        <span className={`status-chip ${isBlocked ? 'chip-blocked' : ''}`}>
          <span className={`status-dot ${provider.health.state === 'offline_ready' ? 'online' : isBlocked ? 'offline' : 'checking'}`} />
          {t(stateTranslationKey[provider.health.state] ?? provider.health.state)}
        </span>
      </div>
      <h3>{provider.name}</h3>
      <p className="record-description">{provider.description}</p>
      <div className="record-meta provider-meta">
        <span>{t('providerCompliance')}: {provider.compliance_note}</span>
        <span>{provider.is_paid ? t('providerPaid') : t('providerFree')}</span>
        <span>{t('providerModel')}: {provider.config.model ?? t('unconfigured')}</span>
        <span>{t('providerCredential')}: {provider.config.credential?.reference ?? t('providerCredentialMissing')}</span>
        <span>{provider.health.credential_available ? t('providerCredentialAvailable') : t('providerCredentialUnavailable')}</span>
        <span>{t('providerLiveCalls')}: {t('providerLiveCallsOff')}</span>
      </div>
      <details className="provider-reasons">
        <summary>{t('providerReasons')}</summary>
        <ul>{provider.health.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
      </details>
      {isBlocked ? (
        <p className="form-note">{t('providerArenaBlocked')}</p>
      ) : (
        <form className="provider-config-form" onSubmit={save}>
          <label className="field"><span>{t('providerModelHint')}</span><input value={model} maxLength={120} onChange={(event) => setModel(event.target.value)} placeholder={provider.config.model ?? ''} /></label>
          <label className="field"><span>{t('providerCredentialHint')}</span><input value={credential} maxLength={200} onChange={(event) => setCredential(event.target.value)} placeholder="env:ANTHROPIC_API_KEY" /></label>
          <label className="checkbox-field">
            <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
            <span>{enabled ? t('providerDisable') : t('providerEnable')}</span>
          </label>
          <div className="form-actions">
            <button className="button button-secondary" type="submit" disabled={mutation.isPending}>{t('providerSaveConfig')}</button>
          </div>
          {mutation.isSuccess && <p className="form-success"><Check size={13} />{t('providerUpdated')}</p>}
          {mutation.isError && <p className="form-error">{t('requestFailed')}: {mutation.error.message}</p>}
        </form>
      )}
    </article>
  )
}

function RouteResult({ decision }: { decision: RouteDecision }) {
  const { t, i18n } = useTranslation()
  return (
    <div className={`decision-panel ${decision.status === 'selected' ? 'decision-ok' : 'decision-denied'}`}>
      <div className="decision-head">
        <span className="decision-icon">{decision.status === 'selected' ? <Check size={16} /> : <CircleAlert size={16} />}</span>
        <div>
          <strong>{decision.status === 'selected' ? t('routingResultSelected') : t('routingResultNone')}</strong>
          <span>{decision.provider_id ? `${decision.provider_id} · ${decision.model ?? ''}` : t(policyTranslationKey[decision.policy])}</span>
        </div>
        {decision.cost && <span className="decision-cost">{t('routingEstimatedCost')}: {money(decision.cost.estimated_cost_usd, i18n.language)}</span>}
      </div>
      <div className="decision-note"><ArrowRight size={13} />{t('routingNoExecution')}</div>
      <ul className="decision-reasons">{decision.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
      <div className="candidate-list">
        <span className="panel-kicker">{t('routingCandidates')}</span>
        {decision.candidates.map((candidate, index) => (
          <div className="inline-row" key={`${candidate.provider_id}-${index}`}>
            <span>{candidate.provider_id} · {candidate.allowed ? t('routingAllowed') : t('routingDenied')}</span>
            <strong>{candidate.estimated_cost_usd !== undefined ? money(candidate.estimated_cost_usd, i18n.language) : '—'}</strong>
          </div>
        ))}
      </div>
    </div>
  )
}
