/**
 * @vitest-environment jsdom
 *
 * A render smoke test: it mounts the real <App /> against mocked API responses
 * and asserts that every view renders without throwing.
 *
 * This closes a gap that HTTP status checks cannot: a view can return 200 from
 * every endpoint and still crash the browser on a null field or a broken hook.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nextProvider } from 'react-i18next'

import i18n from './i18n'

const agent = {
  id: 'agent-1', name: 'Worker One', role: 'developer', description: '',
  system_instructions: '', provider: 'unconfigured', model: null, status: 'idle',
  permissions: ['task:read'], is_manager: false,
  created_at: '2026-11-13T10:00:00Z', updated_at: '2026-11-13T10:00:00Z',
}
const manager = { ...agent, id: 'manager', name: 'Manager', role: 'manager', is_manager: true }
const project = {
  id: 'project-1', name: 'Demo', description: 'A demo project',
  created_at: '2026-11-13T10:00:00Z', updated_at: '2026-11-13T10:00:00Z',
}
const task = {
  id: 'task-1', project_id: 'project-1', title: 'Do the thing', description: '',
  priority: 'normal', state: 'assigned', assigned_agent_id: 'agent-1',
  dependencies: [], acceptance_criteria: [], retry_count: 0, output: null, error: null,
  cancel_requested_at: null, cancel_reason: null,
  created_at: '2026-11-13T10:00:00Z', updated_at: '2026-11-13T10:00:00Z',
}

const responses: Record<string, unknown> = {
  '/api/v1/health': { status: 'ok', application: 'AATM', version: '0.1.0', database: 'ok' },
  '/api/v1/dashboard': {
    projects: { total: 1 },
    agents: { total: 2, workers: 1, max_workers: 20, by_status: { idle: 2 } },
    tasks: { total: 1, by_state: { assigned: 1 } },
    recent_events: [],
  },
  '/api/v1/projects': [project],
  '/api/v1/agents': [manager, agent],
  '/api/v1/tasks': [task],
  '/api/v1/events': [],
  '/api/v1/agent-roles': [{ id: 'developer', name: 'Developer', description: 'Builds things' }],
  '/api/v1/workflow': { transitions: { assigned: ['running', 'cancelled'] }, note: 'validated' },
  '/api/v1/tasks/ready': { tasks: [task], note: 'assigned work whose dependencies are met' },
  '/api/v1/projects/project-1/workspace/tasks/task-1/integrate': {
    task_id: 'task-1', integrated: true, already_integrated: false, branch: 'review/task',
    base_commit: 'a'.repeat(40), head_commit: 'b'.repeat(40), note: 'fast-forwarded',
  },
  '/api/v1/projects/project-1/workspace/tasks/task-1/diff': {
    task_id: 'task-1', available: true, note: 'capped patch',
    preview: {
      task_id: 'task-1', base_commit: 'a'.repeat(40), head_commit: 'b'.repeat(40),
      diff: 'diff --git a/README.md b/README.md\\n+task patch line\\n',
      truncated: false, max_bytes: 262144,
      untracked_files: [{ path: 'new.txt', size_bytes: 20, content: 'new untracked preview', status: 'text', truncated: false }],
      untracked_included: true, untracked_truncated: false, untracked_max_bytes: 131072, note: 'read-only',
    },
  },
  '/api/v1/orchestrator': {
    counts: { running: 0, waiting_for_retry: 0, expired_leases: 0, assigned: 1 },
    leases: [], note: 'no executor is configured',
  },
  '/api/v1/memory': { entries: [], note: 'project-isolated', retrieval: 'keyword' },
  '/api/v1/analytics': {
    projects: { total: 1 }, tasks: { total: 1, by_state: { assigned: 1 } },
    cycle_time: { samples: 0, average_seconds: null, median_seconds: null, max_seconds: null },
    review_outcomes: { total: 0, by_verdict: {}, approval_rate: null, source: 'review_records' },
    rework: { tasks_with_rework: 0, rework_events: 0, task_total: 1, share: 0, source: 'task_transitions' },
    approvals: { by_status: {}, by_kind: {}, note: 'recorded only' },
    throughput: { days: 14, start: '2026-11-01T00:00:00Z', buckets: [], total: 0, source: 'task_transitions' },
    activity: { days: 14, buckets: [], total: 0, source: 'audit_events' },
    notes: ['Every figure is computed from stored rows.'],
  },
  '/api/v1/intelligence': {
    period: { days: 90, since: '2026-08-15T00:00:00Z', until: '2026-11-13T00:00:00Z' },
    agents: [{
      agent_id: 'agent-1', name: 'Worker One', role: 'developer', provider: 'unconfigured', model: null,
      is_manager: false,
      tasks: { total: 1, terminal: 0, open: 1, success: 0, failed: 0, cancelled: 0 },
      success_rate: null, success_rate_denominator: 'terminal successes + failures; cancellations are excluded',
      sample_sufficient: false, complexity_points: 2, complexity_points_per_task: null,
      by_complexity: { normal: 1 }, rework: { events: 0, rate: null },
      reviews: { received: 0, approved: 0, pass_rate: null },
      completion_time: { samples: 0, median_seconds: null, fastest_seconds: null, slowest_seconds: null },
      usage: { records: 0, estimated_cost_usd: 0, confirmed: false, note: 'Estimates only.' },
    }],
    by_role: { developer: [] }, by_complexity: { normal: 1 }, assessments: [],
    method: {
      measured_fields: ['tasks'], assessed_fields: ['assessments'], assessment_kind: 'rule_based',
      model_generated: false, complexity_weights: { normal: 2 }, min_sample: 3,
      ranking: 'none', note: 'No ranking.',
    },
    note: 'Counted from rows.',
  },
  '/api/v1/browser-profiles': { profiles: [], note: 'directories only', automation_available: false },
  '/api/v1/approvals': { approvals: [], note: 'recorded only' },
  '/api/v1/providers': { providers: [], settings: {}, budget_limits: [], pricing: { rates: {} }, live_requests_allowed: false, note: 'offline' },
  '/api/v1/settings': { settings: { language: 'en', theme: 'dark' }, note: 'allow-listed only' },
  '/api/v1/recovery': {
    database: { ok: true, elapsed_ms: 0.4, slow: false, category: 'ok', note: 'ok', integrity: { ok: true, result: 'ok' } },
    queue: { by_state: { assigned: 1 }, recoverable_tasks: 0, exhausted_tasks: 0, running_with_lease: 0, retry_ceiling: 3, note: 'ok' },
    capabilities: [],
    summary: { detected: 0, automatic: 0, not_applicable: [] },
    idempotency: 'No external effect exists.', checked_at: '2026-11-13T10:00:00Z', note: 'Read from real state.',
  },
  '/api/v1/usage': { total_records: 0, by_provider: {}, records: [], billing_note: 'Estimates only; no confirmed billing.' },
  '/api/v1/orchestrator/status': {
    executor: { configured: false, name: 'DisabledExecutor', reason: 'disabled', enabled_by: null, allowed_programs: [] },
    counts: { running: 0, waiting_for_retry: 0, expired_leases: 0, assigned: 0, failed: 0 },
    leases: [], retry_queue: [],
    concurrency: { adaptive_enabled: false, configured_max: 1, recommended_max: null, in_flight: 0, effective_dispatch_budget: 1, applied_automatically: false, reasons: [], note: 'off' },
    checked_at: '2026-11-13T10:00:00Z', note: 'off',
  },
  '/api/v1/system/resources': {
    snapshot: { cpu_percent: 12, load_average_1m: 0.4, cpu_count: 4, memory_total_mb: 8000, memory_available_mb: 4000, memory_used_ratio: 0.5, disk_total_gb: 100, disk_free_gb: 60, disk_used_ratio: 0.4, measured_at: '2026-11-13T10:00:00Z' },
    recommendation: { recommended_concurrency: 2, configured_max: 2, in_flight: 0, reasons: ['normal load'], applied_automatically: false, note: 'Advisory only.' },
    orchestrator: { default_lease_seconds: 60, max_retries: 3, note: 'leases' },
    telemetry: 'Local sampling only.',
  },
}

// React logs a render error to console.error and unmounts the subtree instead of
// throwing, so a naive smoke test passes even when a view crashes. These guards
// turn that console error into a test failure, and capture window errors too.
const consoleErrors: string[] = []
const windowErrors: unknown[] = []

/**
 * jsdom has no EventSource. This stub records every connection so tests can see
 * which cursor the panel resumed with, and can emit frames on demand.
 */
class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  private listeners = new Map<string, ((event: MessageEvent) => void)[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, handler: (event: MessageEvent) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), handler])
  }

  close() { this.closed = true }

  emit(type: string, data: unknown) {
    for (const handler of this.listeners.get(type) ?? []) {
      handler({ data: JSON.stringify(data) } as MessageEvent)
    }
  }
}

beforeEach(async () => {
  responses['/api/v1/tasks'] = [task]
  responses['/api/v1/tasks/task-1/reviews'] = { reviews: [], note: 'reviews' }
  consoleErrors.length = 0
  windowErrors.length = 0
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
    consoleErrors.push(args.map(String).join(' '))
  })
  vi.stubGlobal('addEventListener', (type: string, handler: EventListener) => {
    if (type === 'error') (window as unknown as { __onerror?: EventListener }).__onerror = handler
  })
  window.addEventListener('error', (event) => windowErrors.push(event))
  await i18n.changeLanguage('en')
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const path = url.split('?')[0]
    const body = responses[path]
    if (body === undefined) {
      return new Response(JSON.stringify({ detail: `unmocked: ${path}` }), { status: 404 })
    }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

/** Assert nothing crashed during the render. */
function expectNoCrash() {
  const renderErrors = consoleErrors.filter((line) =>
    /cannot read|undefined is not|is not a function|Rendered more hooks|Maximum update/i.test(line))
  expect(renderErrors).toEqual([])
  expect(windowErrors).toEqual([])
  expect(screen.queryByText(/something went wrong/i)).toBeNull()
}

async function renderApp() {
  const { default: App } = await import('./App')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>
    </I18nextProvider>,
  )
}

describe('application render smoke test', () => {
  it('renders the dashboard without throwing', async () => {
    await renderApp()
    await waitFor(() => expect(screen.getAllByText(/AATM/i).length).toBeGreaterThan(0))
    expectNoCrash()
  })

  it('renders every navigation section without throwing', async () => {
    const { container } = await renderApp()
    // The shell renders once the health query resolves, so wait for the nav.
    await waitFor(() => expect(container.querySelector('nav.primary-nav')).not.toBeNull())
    const buttons = [...container.querySelectorAll('nav.primary-nav button')]
    expect(buttons.length).toBeGreaterThan(6)

    let changed = 0
    for (const button of buttons) {
      // The already-active entry re-renders to the same markup; skip it so the
      // "markup must change" assertion below stays meaningful.
      if (button.classList.contains('active')) continue
      const before = container.innerHTML
      ;(button as HTMLButtonElement).click()
      await waitFor(() => expect(container.innerHTML).not.toBe(before), { timeout: 3000 })
      // The main region must keep real content after the swap.
      expect((container.querySelector('main')?.innerHTML.length ?? 0)).toBeGreaterThan(100)
      changed += 1
    }
    // Guard against a vacuous pass: nearly every section must have been visited.
    expect(changed).toBeGreaterThanOrEqual(buttons.length - 1)
    expectNoCrash()
  })

  it('loads and shows a task diff only after the operator opens the preview', async () => {
    const { container } = await renderApp()
    await waitFor(() => expect(container.querySelector('nav.primary-nav')).not.toBeNull())
    const tasksButton = [...container.querySelectorAll('nav.primary-nav button')]
      .find((button) => button.textContent?.trim() === 'Tasks')
    expect(tasksButton).toBeDefined()
    fireEvent.click(tasksButton!)

    const showDiff = await screen.findByRole('button', { name: 'Review task diff' })
    const fetchMock = vi.mocked(globalThis.fetch)
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/workspace/tasks/task-1/diff'))).toBe(false)
    fireEvent.click(showDiff)
    expect(await screen.findByText(/task patch line/)).toBeTruthy()
    expect(await screen.findByText(/new untracked preview/)).toBeTruthy()
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/workspace/tasks/task-1/diff'))).toBe(true)
    expectNoCrash()
  })

  it('offers explicit integration only when the current task commit has an approved review', async () => {
    const diffPath = '/api/v1/projects/project-1/workspace/tasks/task-1/diff'
    const diffBody = responses[diffPath] as { preview: Record<string, unknown> }
    responses[diffPath] = {
      ...diffBody,
      preview: { ...diffBody.preview, untracked_files: [], untracked_included: false },
    }
    responses['/api/v1/tasks'] = [{ ...task, state: 'approved' }]
    responses['/api/v1/tasks/task-1/reviews'] = {
      reviews: [{
        id: 'review-1', task_id: 'task-1', reviewer_agent_id: 'agent-2', verdict: 'approved',
        summary: 'Reviewed', checks: [{ check: 'diff', result: 'pass' }],
        task_worktree_head: 'b'.repeat(40), created_at: '2026-11-13T10:00:00Z',
      }],
      note: 'reviews',
    }
    const confirmMock = vi.fn((): boolean => false)
    vi.stubGlobal('confirm', confirmMock)
    const { container } = await renderApp()
    await waitFor(() => expect(container.querySelector('nav.primary-nav')).not.toBeNull())
    const tasksButton = [...container.querySelectorAll('nav.primary-nav button')]
      .find((button) => button.textContent?.trim() === 'Tasks')
    fireEvent.click(tasksButton!)
    fireEvent.click(await screen.findByRole('button', { name: 'Review task diff' }))
    const integrateButton = await screen.findByRole('button', { name: 'Integrate approved commit' })

    fireEvent.click(integrateButton)
    expect(confirmMock).toHaveBeenCalledOnce()
    const fetchMock = vi.mocked(globalThis.fetch)
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/workspace/tasks/task-1/integrate'))).toBe(false)

    confirmMock.mockReturnValue(true)
    fireEvent.click(integrateButton)
    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) =>
      String(input).includes('/workspace/tasks/task-1/integrate') && init?.method === 'POST',
    )).toBe(true))
    expect(await screen.findByText('Approved commit integrated into branch review/task.')).toBeTruthy()
    expectNoCrash()
  })

  it('renders right-to-left without throwing', async () => {
    await i18n.changeLanguage('ar')
    await renderApp()
    await waitFor(() => expect(document.querySelector('[dir="rtl"]')).not.toBeNull())
    expectNoCrash()
  })
})
