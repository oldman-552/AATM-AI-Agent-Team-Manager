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
  permissions: string[]
  is_manager: boolean
  created_at: string
  updated_at: string
}

export type AgentRole = { id: string; name: string; description: string }

export type AgentCenterEntry = {
  agent_id: string
  name: string
  role: string
  is_manager: boolean
  status: string
  provider: string
  model: string | null
  current_task: { task_id: string; title: string; state: string; priority: string; updated_at: string; lease_owner: string | null } | null
  open_task_count: number
  open_tasks: { task_id: string; title: string; state: string; priority: string }[]
  latest_activity: { at: string; event_type: string; summary: string; entity_type: string; entity_id: string } | null
  execution_time: { seconds: number | null; basis: string }
  usage: { records: number; estimated_cost_usd: number; confirmed_cost_usd: number; confirmed_records: number; input_tokens: number; output_tokens: number; cost_source: string }
  leases: { held: boolean; task_id: string | null; owner: string | null; expires_at: string | null }
  browser: { profiles: number; names: string[]; automation_available: boolean; note: string }
  authentication: { registered: boolean; provider_configured: boolean; model: string | null; note: string }
  errors: { task_id: string; state: string; error: string | null }[]
  history: { task_id: string; title: string; state: string; updated_at: string }[]
  controls: Record<string, boolean | string | null>
  honesty: Record<string, string | boolean>
}

export type BlueprintPlan = {
  idea: string
  options: { scale: 'prototype' | 'mvp' | 'production'; stack: 'python-react' | 'node-react' | 'python-only'; data_layer: 'sqlite' | 'postgres'; team_size: number }
  requirements: { id: string; text: string; source: string }[]
  architecture: { shape: string; layers: string[]; constraints: string[]; data_layer_choice: string }
  technology_stack: Record<string, string>
  database_design: { table: string; columns: string[]; why: string; refine?: string }[]
  development_phases: { name: string; tasks: string[]; exit_criteria: string }[]
  task_breakdown: { key: string; order: number; title: string; role: string; phase: string; depends_on: string[]; acceptance_criteria: string[]; description: string }[]
  assignment_plan: { task_key: string; role: string; agent_id: string | null; agent_name: string | null; reason: string }[]
  dependencies: { from: string; to: string; type: string }[]
  testing_strategy: string[]
  acceptance_criteria: string[]
  delivery_plan: { milestone: string; exit_criteria: string; task_count: number; gate: string }[]
  detection_evidence: Record<string, string[]>
  generation: { generated_by: string; model_called: boolean; note: string; requires_review: boolean; auto_execution: boolean }
  fingerprint: string
  summary: { requirements: number; tasks: number; phases: number; capability_packs: string[]; staffed_tasks: number; unstaffed_tasks: number; project_name: string }
}

export type AgentInstruction = {
  id: string
  task_id: string | null
  instruction: string
  issued_by: string
  delivered: boolean
  created_at: string
}

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
  cancel_requested_at?: string | null
  cancel_reason?: string | null
  created_at: string
  updated_at: string
}

export type TimelineEntry = {
  at: string
  kind: 'transition' | 'checkpoint' | 'audit' | 'review' | 'approval'
  title_key: string
  data: Record<string, unknown>
  detail: string | null
  reference: string
  source: string
}

export type TaskTimeline = {
  task_id: string
  entries: TimelineEntry[]
  total: number
  truncated: boolean
  sources: string[]
  note: string
}

export type TaskCheckpoint = {
  id: string
  task_id: string
  sequence: number
  label: string
  state: Record<string, unknown>
  note: string
  created_at: string
}

export type ResumePlan = {
  task_id: string
  state: string
  retry_count: number
  lease_expires_at: string | null
  checkpoint_count: number
  latest_checkpoint: TaskCheckpoint | null
  next_actions: string[]
  resumed_automatically: false
}

export type PullRequestPlan = {
  id: string
  project_id: string
  owner: string
  repo: string
  repository: string
  base_branch: string
  head_branch: string
  title: string
  body: string
  status: 'awaiting_approval' | 'approved_not_executed' | 'rejected'
  approval_id: string | null
  executed: boolean
  execution_available: boolean
  execution_reason: string
  commands: string[]
  created_at: string
}

export type AnalyticsOverview = {
  counts: {
    projects: number
    agents: number
    tasks: number
    tasks_active: number
    tasks_terminal: number
    checkpoints: number
  }
  throughput: { days: number; start: string; buckets: { date: string; completed: number; approved: number; cancelled: number }[]; total: number; source: string }
  activity: { days: number; buckets: { date: string; events: number }[]; total: number; source: string }
  cycle_time: { samples: number; average_seconds: number | null; median_seconds: number | null; max_seconds: number | null }
  reviews: { total: number; by_verdict: Record<string, number>; approval_rate: number | null; source: string }
  rework: { tasks_with_rework: number; rework_events: number; task_total: number; share: number | null; source: string }
  approvals: { by_status: Record<string, number>; by_kind: Record<string, number>; pending: number; source: string }
  notes: string[]
}

export type NotificationItem = {
  id: string
  kind: 'approval_pending' | 'task_needs_attention' | 'lease_expired'
  entity_type: string
  entity_id: string | null
  message_key: string
  data: Record<string, unknown>
  action_view: 'approvals' | 'tasks'
  severity: 'attention' | 'warning' | 'error'
  created_at: string | null
  read: boolean
  read_at: string | null
}

export type NotificationSummary = {
  notifications: NotificationItem[]
  unread: number
  total: number
  source: string
}

export type AppPreferences = {
  language: string
  theme: 'dark' | 'light'
  page_size: number
  notification_poll_seconds: number
  checkpoint_retention: number
  backup_retention: number
  updated_at: string | null
}

export type ManagerPlan = {
  project_id: string | null
  task_total: number
  queued_total: number
  active_agents: number
  findings: { code: string; severity: 'error' | 'warning' | 'info'; task_id?: string; task_title?: string; task_ids?: string[]; blocking?: string[] }[]
  proposals: {
    task_id: string
    task_title: string
    current_state: string
    current_agent_id: string | null
    suggested_agent_id: string | null
    reason_code: string
    reason_data: Record<string, unknown>
  }[]
  order: string[]
  dependency_cycles: string[]
  generated_at: string
  planner: string
  applies_automatically: false
  plan_id: string
}

export type AgentScopeList = { scopes: string[]; default: string; note: string }

export type BrowserProfile = {
  id: string
  name: string
  label: string
  agent_id: string | null
  isolation: 'per_profile' | 'shared_readonly'
  status: 'created' | 'ready' | 'locked' | 'archived'
  locked_by: string | null
  locked_at: string | null
  session_state: string
  created_at: string | null
  updated_at: string | null
  directory: string
  exists: boolean
  size_bytes: number
  entries: number
  modified_at: string | null
  automation_available: false
  automation_reason: string
  credentials_inspected: false
  credentials_note: string
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

export type ResourceSnapshot = {
  cpu_percent: number | null
  load_average_1m: number | null
  cpu_count: number
  memory_total_mb: number | null
  memory_available_mb: number | null
  memory_used_ratio: number | null
  disk_total_gb: number | null
  disk_free_gb: number | null
  disk_used_ratio: number | null
  measured_at: string
}

export type ResourceReport = {
  snapshot: ResourceSnapshot
  recommendation: {
    recommended_concurrency: number
    configured_max: number
    in_flight: number
    reasons: string[]
    applied_automatically: boolean
    note: string
  }
  orchestrator: { default_lease_seconds: number; max_retries: number; note: string }
  telemetry: string
}

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
  buildBlueprint: (payload: { idea: string; scale: string; stack: string; data_layer: string; team_size: number; project_name?: string }) =>
    request<BlueprintPlan>('/api/v1/blueprints', { method: 'POST', body: JSON.stringify(payload) }),
  applyBlueprint: (plan: BlueprintPlan, projectName?: string) =>
    request<{ project_id: string | null; project_name: string | null; tasks_created: number; first_task_id: string | null; note: string }>(
      '/api/v1/blueprints/apply',
      { method: 'POST', body: JSON.stringify({ plan, confirmed: true, project_name: projectName ?? null }) },
    ),
  agentCenter: () => request<{ agents: AgentCenterEntry[]; total: number; note: string }>('/api/v1/agents/center'),
  agentCenterEntry: (id: string) => request<AgentCenterEntry>(`/api/v1/agents/${id}/center`),
  agentInstructions: (id: string) =>
    request<{ instructions: AgentInstruction[]; delivery_note: string }>(`/api/v1/agents/${id}/instructions`),
  issueInstruction: (id: string, instruction: string, taskId?: string | null) =>
    request<{ id: string; delivered: boolean; note: string }>(`/api/v1/agents/${id}/instructions`, {
      method: 'POST',
      body: JSON.stringify({ instruction, task_id: taskId ?? null }),
    }),
  reassignTask: (agentId: string, taskId: string, toAgentId: string | null, note: string) =>
    request<{ task_id: string; from_agent_id: string | null; to_agent_id: string | null; state: string }>(
      `/api/v1/agents/${agentId}/reassign`,
      { method: 'POST', body: JSON.stringify({ task_id: taskId, to_agent_id: toAgentId, note }) },
    ),
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
  taskTimeline: (taskId: string, limit = 200) =>
    request<TaskTimeline>(`/api/v1/tasks/${taskId}/timeline?limit=${limit}`),
  requestCancel: (taskId: string, reason: string) =>
    request<{ task_id: string; cancel_requested_at: string | null; cancel_reason: string | null; state: string; note: string }>(
      `/api/v1/tasks/${taskId}/cancel`,
      { method: 'POST', body: JSON.stringify({ reason }) },
    ),
  withdrawCancel: (taskId: string) =>
    request<{ task_id: string; state: string }>(`/api/v1/tasks/${taskId}/cancel`, { method: 'DELETE' }),
  applyCancel: (taskId: string) =>
    request<{ task_id: string; cancelled: boolean; state?: string; reason?: string }>(`/api/v1/tasks/${taskId}/cancel/apply`, {
      method: 'POST',
    }),
  pendingCancellations: () =>
    request<{ pending: { task_id: string; title: string; state: string; reason: string | null; requested_at: string | null }[] }>(
      '/api/v1/cancellations',
    ),
  taskTransitions: (taskId: string) =>
    request<{ transitions: Array<Record<string, unknown>> }>(`/api/v1/tasks/${taskId}/transitions`),
  events: () => request<AuditEvent[]>('/api/v1/events'),
  orchestratorStatus: () => request<OrchestratorStatus>('/api/v1/orchestrator/status'),
  browserProfiles: () => request<{ profiles: BrowserProfile[]; automation_available: boolean; note: string }>(
    '/api/v1/browser-profiles',
  ),
  createBrowserProfile: (payload: { name: string; label?: string; agent_id?: string | null }) =>
    request<{ profile: BrowserProfile }>('/api/v1/browser-profiles', { method: 'POST', body: JSON.stringify(payload) }),
  lockBrowserProfile: (id: string, lockedBy: string) =>
    request<{ profile: BrowserProfile }>(`/api/v1/browser-profiles/${id}/lock`, {
      method: 'POST', body: JSON.stringify({ locked_by: lockedBy }),
    }),
  unlockBrowserProfile: (id: string) =>
    request<{ profile: BrowserProfile }>(`/api/v1/browser-profiles/${id}/unlock`, { method: 'POST' }),
  deleteBrowserProfile: (id: string) =>
    request<{ deleted: boolean; name: string; removed_bytes: number }>(
      `/api/v1/browser-profiles/${id}?confirm=true`, { method: 'DELETE' },
    ),
  agentScopes: () => request<AgentScopeList>('/api/v1/agents/scopes'),
  changeAgentState: (agentId: string, targetState: string) =>
    request<{ agent_id: string; status: string }>(`/api/v1/agents/${agentId}/state`, {
      method: 'PATCH',
      body: JSON.stringify({ target_state: targetState }),
    }),
  changeAgentPermissions: (agentId: string, permissions: string[]) =>
    request<{ agent_id: string; permissions: string[] }>(`/api/v1/agents/${agentId}/permissions`, {
      method: 'PATCH',
      body: JSON.stringify({ permissions }),
    }),
  managerPlan: (projectId?: string) =>
    request<ManagerPlan>(`/api/v1/planning/proposals${projectId ? `?project_id=${projectId}` : ''}`),
  applyManagerPlan: (plan: Record<string, unknown>, actor = 'manager') =>
    request<{ applied: { task_id: string; agent_id: string }[]; skipped: { task_id: string; reason: string }[]; plan_id: string }>(
      '/api/v1/planning/apply',
      { method: 'POST', body: JSON.stringify({ plan, actor }) },
    ),
  settings: () => request<{ settings: AppPreferences; defaults: Record<string, unknown>; note: string }>('/api/v1/settings'),
  updateSettings: (payload: Record<string, string | number>) =>
    request<{ settings: AppPreferences }>('/api/v1/settings', { method: 'PATCH', body: JSON.stringify(payload) }),
  resetSettings: () => request<{ settings: AppPreferences }>('/api/v1/settings/reset', { method: 'POST' }),
  notifications: () => request<NotificationSummary>('/api/v1/notifications'),
  markNotificationsRead: (ids: string[]) =>
    request<NotificationSummary & { marked_read: number }>('/api/v1/notifications/read', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),
  markAllNotificationsRead: () =>
    request<NotificationSummary & { marked_read: number }>('/api/v1/notifications/read-all', { method: 'POST' }),
  analytics: (days = 14) => request<AnalyticsOverview>(`/api/v1/analytics?days=${days}`),
  resources: (configuredMax = 2) => request<ResourceReport>(`/api/v1/system/resources?configured_max=${configuredMax}`),
  checkpoints: (taskId: string) => request<{ task_id: string; checkpoints: TaskCheckpoint[] }>(`/api/v1/tasks/${taskId}/checkpoints`),
  createCheckpoint: (taskId: string, payload: { label: string; note?: string; state?: Record<string, unknown> }) =>
    request<{ checkpoint: TaskCheckpoint; created: boolean }>(`/api/v1/tasks/${taskId}/checkpoints`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  resumePlan: (taskId: string) => request<ResumePlan>(`/api/v1/tasks/${taskId}/resume-plan`),
  pullRequestPlans: (projectId: string) =>
    request<{ plans: PullRequestPlan[]; execution_available: boolean; execution_reason: string }>(
      `/api/v1/projects/${projectId}/pull-requests`,
    ),
  createPullRequestPlan: (projectId: string, payload: {
    owner: string; repo: string; base_branch: string; head_branch: string; title: string; body?: string
  }) => request<{ plan: PullRequestPlan; approval: { id: string; status: string } }>(
    `/api/v1/projects/${projectId}/pull-requests`,
    { method: 'POST', body: JSON.stringify(payload) },
  ),
  decidePullRequestPlan: (projectId: string, planId: string, payload: { status: 'approved' | 'rejected'; decided_by: string }) =>
    request<{ plan: PullRequestPlan }>(`/api/v1/projects/${projectId}/pull-requests/${planId}/decision`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
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
