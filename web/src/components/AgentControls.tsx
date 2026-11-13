import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { KeyRound, Play, Pause, Power, ShieldCheck } from 'lucide-react'

import { api, Agent } from '../api'

const NEXT_STATES: Record<string, string[]> = {
  idle: ['active', 'disabled'],
  active: ['paused', 'disabled'],
  paused: ['active', 'disabled'],
  disabled: [],
  offline: [],
}

const SCOPE_LABELS: Record<string, string> = {
  'task:read': 'scopeTaskRead',
  'task:write': 'scopeTaskWrite',
  'task:assign': 'scopeTaskAssign',
  'review:submit': 'scopeReviewSubmit',
  'memory:write': 'scopeMemoryWrite',
  'workspace:write': 'scopeWorkspaceWrite',
}

/**
 * Lifecycle and permission controls. The server rejects every illegal state
 * change and every unknown scope; this UI only offers what the API allows.
 */
export function AgentControls({ agent }: { agent: Agent }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<string[]>(agent.permissions ?? [])

  const scopes = useQuery({ queryKey: ['agentScopes'], queryFn: api.agentScopes })

  const stateChange = useMutation({
    mutationFn: (target: string) => api.changeAgentState(agent.id, target),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['agents'] }),
        queryClient.invalidateQueries({ queryKey: ['blockedAgents'] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
      ])
    },
  })
  const permissions = useMutation({
    mutationFn: (next: string[]) => api.changeAgentPermissions(agent.id, next),
    onSuccess: async () => {
      setEditing(false)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['agents'] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
      ])
    },
  })

  if (agent.is_manager) return null
  const available = NEXT_STATES[agent.status] ?? []

  return (
    <div className="agent-controls">
      <div className="agent-control-row">
        {available.includes('active') && (
          <button className="button button-secondary task-action-button" type="button" disabled={stateChange.isPending}
            onClick={() => stateChange.mutate('active')}>
            <Play size={11} /> {t('agentActivate')}
          </button>
        )}
        {available.includes('paused') && (
          <button className="button button-secondary task-action-button" type="button" disabled={stateChange.isPending}
            onClick={() => stateChange.mutate('paused')}>
            <Pause size={11} /> {t('agentPause')}
          </button>
        )}
        {available.includes('disabled') && (
          <button className="button button-secondary task-action-button" type="button" disabled={stateChange.isPending}
            onClick={() => stateChange.mutate('disabled')}>
            <Power size={11} /> {t('agentDisable')}
          </button>
        )}
        <button className="button button-secondary task-action-button" type="button" onClick={() => setEditing((value) => !value)}>
          <KeyRound size={11} /> {t('agentPermissions')}
        </button>
      </div>

      <div className="agent-scope-list">
        {(agent.permissions ?? []).length === 0 ? (
          <span className="agent-scope empty"><ShieldCheck size={10} /> {t('agentNoPermissions')}</span>
        ) : (
          (agent.permissions ?? []).map((scope) => (
            <span className="agent-scope" key={scope}>{t(SCOPE_LABELS[scope] ?? scope)}</span>
          ))
        )}
      </div>

      {editing && (
        <div className="agent-scope-editor">
          {scopes.data?.scopes.map((scope) => (
            <label key={scope}>
              <input
                type="checkbox"
                checked={draft.includes(scope)}
                onChange={(event) => setDraft((current) =>
                  event.target.checked ? [...current, scope] : current.filter((item) => item !== scope))}
              />
              <span>{t(SCOPE_LABELS[scope] ?? scope)}</span>
            </label>
          ))}
          <div className="agent-scope-actions">
            <button className="button button-primary task-action-button" type="button" disabled={permissions.isPending}
              onClick={() => permissions.mutate(draft)}>
              {t('save')}
            </button>
            <span className="form-note">{t('agentDenyByDefault')}</span>
          </div>
        </div>
      )}

      {stateChange.isError && <p className="form-error">{t('requestFailed')}: {stateChange.error.message}</p>}
      {permissions.isError && <p className="form-error">{t('requestFailed')}: {permissions.error.message}</p>}
    </div>
  )
}
