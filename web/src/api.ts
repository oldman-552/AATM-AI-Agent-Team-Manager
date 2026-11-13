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
}
