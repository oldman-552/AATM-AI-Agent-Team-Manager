export type Project = {
  id: string
  name: string
  description: string
  status: string
  created_at: string
  updated_at: string
}

export type Agent = {
  id: string
  name: string
  role: string
  description: string
  system_instructions: string
  provider: string
  model: string | null
  status: string
  is_manager: boolean
  created_at: string
  updated_at: string
}

export type AgentRole = { id: string; name: string; description: string }

export type Task = {
  id: string
  project_id: string | null
  title: string
  description: string
  priority: 'low' | 'normal' | 'high' | 'urgent'
  state: string
  assigned_agent_id: string | null
  dependencies: string[]
  acceptance_criteria: string[]
  retry_count: number
  output: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export type AuditEvent = {
  id: string
  entity_type: string
  entity_id: string | null
  event_type: string
  summary: string
  created_at: string
}

export type Dashboard = {
  projects: { total: number }
  agents: { total: number; workers: number; max_workers: number; by_status: Record<string, number> }
  tasks: { total: number; by_state: Record<string, number> }
  recent_events: AuditEvent[]
}

export type Health = {
  status: string
  application: string
  version: string
  database: string
}

export type RoutingPolicy = 'arena_first' | 'claude_first' | 'manual' | 'task_based' | 'user_defined'
export type TaskComplexity = 'low' | 'medium' | 'high'
export type ProviderState = 'offline_ready' | 'unconfigured' | 'disabled' | 'blocked' | 'budget_exhausted' | 'not_permitted'

export type ProviderCredential = { scheme: string; locator: string; reference: string } | null

export type ProviderConfig = {
  provider_id: string
  enabled: boolean
  credential: ProviderCredential
  model: string | null
  base_url: string | null
  live_requests_allowed: boolean
}

export type ProviderHealth = {
  provider_id: string
  state: ProviderState
  enabled: boolean
  credential_available: boolean
  reasons: string[]
  live_calls_enabled: boolean
  checked_at: string
}

export type ProviderDescriptor = {
  id: string
  name: string
  description: string
  is_paid: boolean
  compliance_note: string
  config: ProviderConfig
  health: ProviderHealth
}

export type ProviderSettings = {
  routing_policy: RoutingPolicy
  default_model: string
  user_defined_order: string[]
  live_requests_allowed: boolean
  arena_compliance_verified: boolean
}

export type BudgetLimit = {
  scope: string
  provider_id: string
  scope_key: string | null
  limit_usd: number
  used_usd?: number
  remaining_usd?: number
}

export type CostEstimate = {
  model: string
  input_tokens: number
  output_tokens: number
  estimated_cost_usd: number
  billing_status: string
  confirmed_cost_usd: number | null
}

export type BudgetCheck = {
  allowed: boolean
  reason: string
  estimated_cost_usd: number
  applied_limits: Array<Record<string, unknown>>
}

export type UsageSummary = {
  total_records: number
  by_provider: Record<string, { requests: number; estimated_cost_usd: number; confirmed_cost_usd: number }>
  records: Array<Record<string, unknown>>
  billing_note: string
}

export type ProviderCatalog = {
  providers: ProviderDescriptor[]
  settings: ProviderSettings
  budget_limits: BudgetLimit[]
  pricing: { basis: string; override_environment_variable: string; rates: Record<string, { input_per_million_usd: number; output_per_million_usd: number }> }
  live_requests_allowed: boolean
  note: string
}

export type RouteCandidate = {
  provider_id: string
  health_state?: string
  allowed: boolean
  reason: string
  estimated_cost_usd?: number
}

export type RouteDecision = {
  status: 'selected' | 'no_eligible_provider'
  policy: RoutingPolicy
  provider_id: string | null
  model: string | null
  reasons: string[]
  cost: CostEstimate | null
  budget: BudgetCheck | null
  candidates: RouteCandidate[]
  execution_performed: boolean
}

export type RouteInput = {
  policy?: RoutingPolicy
  preferred_provider?: string | null
  provider_order?: string[]
  complexity?: TaskComplexity
  agent_id?: string | null
  project_id?: string | null
  model?: string | null
  estimated_input_tokens?: number
  estimated_output_tokens?: number
  max_tokens?: number
  paid_consent?: boolean
}

export type TaskStateChangeResult = {
  task: Task
  transition_created: boolean
  allowed_next_states: string[]
}

export type OrchestratorStatus = {
  executor: { configured: boolean; name: string; reason: string }
  counts: {
    running: number
    waiting_for_retry: number
    expired_leases: number
    assigned: number
    failed: number
  }
  leases: Array<{ task_id: string; title: string; lease_owner: string | null; lease_expires_at: string | null; lease_expired: boolean }>
  retry_queue: Array<{ task_id: string; title: string; next_attempt_at: string | null }>
  checked_at: string
  note: string
}

export type ReviewCheck = { check: string; result: string }

export type Review = {
  id: string
  task_id: string
  reviewer_agent_id: string | null
  verdict: 'approved' | 'rework_required'
  summary: string
  checks: ReviewCheck[]
  created_at: string
}

export type Approval = {
  id: string
  kind: string
  entity_type: string
  entity_id: string | null
  summary: string
  status: 'pending' | 'approved' | 'rejected'
  requested_by: string
  decided_by: string | null
  decision_note: string
  requested_at: string
  decided_at: string | null
}

export type WorkspaceStatus = {
  branch: string
  head_commit: string
  on_protected_branch: boolean
  clean: boolean
  changed_files: string[]
  changed_count: number
  diffstat: string
  note: string
}

export type ProjectWorkspace = {
  id: string
  project_id: string
  workspace_path: string
  root_path: string
  branch: string | null
  status: string
}

export type WorkspaceResponse = {
  workspace: ProjectWorkspace | null
  status?: WorkspaceStatus | null
  error?: string
  note?: string
}

export type MemoryScope = 'global' | 'project' | 'agent' | 'task' | 'decision'

export type MemoryEntry = {
  id: string
  project_id: string | null
  scope: MemoryScope
  key: string | null
  title: string
  content: string
  agent_id: string | null
  task_id: string | null
  tags: string[]
  version: number
  created_at: string
  updated_at: string
}

export type MemoryVersion = { version: number; title: string; content: string; created_at: string }

export type MemorySearchResult = { entry: MemoryEntry; score: number }

export type WorkflowDefinition = {
  transitions: Record<string, string[]>
  dependency_satisfied_states: string[]
  evidence_required_states: string[]
  note: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })

  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json() as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // Keep the status-based message when the server returned a non-JSON body.
    }
    throw new Error(message)
  }

  return response.json() as Promise<T>
}

export const api = {
  health: () => request<Health>('/api/v1/health'),
  dashboard: () => request<Dashboard>('/api/v1/dashboard'),
  projects: () => request<Project[]>('/api/v1/projects'),
  createProject: (payload: Pick<Project, 'name' | 'description'>) =>
    request<Project>('/api/v1/projects', { method: 'POST', body: JSON.stringify(payload) }),
  agents: () => request<Agent[]>('/api/v1/agents'),
  agentRoles: () => request<AgentRole[]>('/api/v1/agent-roles'),
  createAgent: (payload: { name: string; role: string; description: string }) =>
    request<Agent>('/api/v1/agents', { method: 'POST', body: JSON.stringify(payload) }),
  tasks: () => request<Task[]>('/api/v1/tasks'),
  createTask: (payload: {
    project_id: string | null
    title: string
    description: string
    priority: Task['priority']
    assigned_agent_id: string | null
  }) => request<Task>('/api/v1/tasks', { method: 'POST', body: JSON.stringify(payload) }),
  workflow: () => request<WorkflowDefinition>('/api/v1/tasks/workflow'),
  readyTasks: () => request<{ tasks: Task[]; note: string }>('/api/v1/tasks/ready'),
  changeTaskState: (taskId: string, payload: { target_state: string; idempotency_key: string; note: string }) =>
    request<TaskStateChangeResult>(`/api/v1/tasks/${taskId}/state`, { method: 'PATCH', body: JSON.stringify(payload) }),
  taskTransitions: (taskId: string) =>
    request<{ transitions: Array<Record<string, unknown>> }>(`/api/v1/tasks/${taskId}/transitions`),
  events: () => request<AuditEvent[]>('/api/v1/events'),
  orchestratorStatus: () => request<OrchestratorStatus>('/api/v1/orchestrator/status'),
  recoverLeases: () => request<{ recovered: string[]; count: number; note: string }>('/api/v1/orchestrator/recover', { method: 'POST' }),
  taskReviews: (taskId: string) => request<{ reviews: Review[]; note: string }>(`/api/v1/tasks/${taskId}/reviews`),
  createReview: (
    taskId: string,
    payload: { reviewer_agent_id: string; verdict: 'approved' | 'rework_required'; summary: string; checks: ReviewCheck[]; idempotency_key: string },
  ) =>
    request<{ review: Review; created: boolean; task_state: string }>(`/api/v1/tasks/${taskId}/reviews`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  approvals: () => request<{ approvals: Approval[]; note: string }>('/api/v1/approvals'),
  createApproval: (payload: { kind: string; entity_type: string; entity_id: string | null; summary: string }) =>
    request<{ approval: Approval }>('/api/v1/approvals', { method: 'POST', body: JSON.stringify(payload) }),
  decideApproval: (approvalId: string, payload: { status: 'approved' | 'rejected'; decided_by: string; note: string }) =>
    request<{ approval: Approval; note: string }>(`/api/v1/approvals/${approvalId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  memory: (projectId: string | null, includeGlobal = true) =>
    request<{ entries: MemoryEntry[]; scopes: MemoryScope[]; isolation: string }>(
      `/api/v1/memory?${new URLSearchParams({
        ...(projectId ? { project_id: projectId } : {}),
        include_global: String(includeGlobal),
      }).toString()}`,
    ),
  saveMemory: (payload: {
    title: string
    content: string
    scope: MemoryScope
    key?: string | null
    project_id?: string | null
    tags?: string[]
  }) => request<{ entry: MemoryEntry; created: boolean }>('/api/v1/memory', { method: 'POST', body: JSON.stringify(payload) }),
  memoryEntry: (entryId: string, projectId: string | null) =>
    request<{ entry: MemoryEntry; history: MemoryVersion[] }>(
      `/api/v1/memory/${entryId}?${new URLSearchParams(projectId ? { project_id: projectId } : {}).toString()}`,
    ),
  rollbackMemory: (entryId: string, version: number, projectId: string | null) =>
    request<{ entry: MemoryEntry }>(
      `/api/v1/memory/${entryId}/rollback/${version}?${new URLSearchParams(projectId ? { project_id: projectId } : {}).toString()}`,
      { method: 'POST' },
    ),
  deleteMemory: (entryId: string, projectId: string | null) =>
    request<{ deleted: boolean; id: string }>(
      `/api/v1/memory/${entryId}?${new URLSearchParams(projectId ? { project_id: projectId } : {}).toString()}`,
      { method: 'DELETE' },
    ),
  searchMemory: (query: string, projectId: string | null) =>
    request<{ results: MemorySearchResult[]; query: string; retrieval: string }>(
      `/api/v1/memory/search?${new URLSearchParams({
        q: query,
        ...(projectId ? { project_id: projectId } : {}),
      }).toString()}`,
    ),
  workspace: (projectId: string) => request<WorkspaceResponse>(`/api/v1/projects/${projectId}/workspace`),
  createWorkspace: (projectId: string, payload: { local_source?: string | null; branch?: string | null }) =>
    request<WorkspaceResponse>(`/api/v1/projects/${projectId}/workspace`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  createWorkspaceBranch: (projectId: string, branch: string) =>
    request<{ branch: string; status: WorkspaceStatus }>(`/api/v1/projects/${projectId}/workspace/branches`, {
      method: 'POST',
      body: JSON.stringify({ branch }),
    }),
  removeWorkspace: (projectId: string) =>
    request<{ removed: boolean; workspace_path: string }>(`/api/v1/projects/${projectId}/workspace`, { method: 'DELETE' }),
  providers: () => request<ProviderCatalog>('/api/v1/providers'),
  providerHealth: (providerId: string) => request<ProviderHealth>(`/api/v1/providers/${providerId}/health`),
  updateProviderConfig: (
    providerId: string,
    payload: { enabled?: boolean; credential_ref?: string; clear_credential?: boolean; model?: string },
  ) =>
    request<{ config: ProviderConfig; health: ProviderHealth }>(`/api/v1/providers/${providerId}/config`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  updateProviderSettings: (payload: { routing_policy: RoutingPolicy }) =>
    request<ProviderSettings>('/api/v1/providers/settings', { method: 'PATCH', body: JSON.stringify(payload) }),
  routeDryRun: (payload: RouteInput) =>
    request<RouteDecision>('/api/v1/providers/route', { method: 'POST', body: JSON.stringify(payload) }),
  budgets: () => request<{ limits: BudgetLimit[]; usage: UsageSummary; note: string }>('/api/v1/budgets'),
  setBudget: (payload: { scope: string; provider_id: string; limit_usd: number; scope_key?: string | null }) =>
    request<{ limit: BudgetLimit; limits: BudgetLimit[] }>('/api/v1/budgets', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  usage: () => request<UsageSummary>('/api/v1/usage'),
}
