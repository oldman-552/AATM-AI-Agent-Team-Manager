import { FormEvent, ReactNode, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  ArrowDownLeft,
  ArrowRight,
  BarChart3,
  BookOpen,
  MonitorSmartphone,
  Settings,
  Bot,
  Check,
  CircleAlert,
  CircleDot,
  Gauge,
  Clock3,
  Command,
  Cpu,
  FileSearch,
  FolderGit2,
  FolderKanban,
  Languages,
  ListTodo,
  LoaderCircle,
  Moon,
  Plus,
  PlugZap,
  ShieldCheck,
  Sparkles,
  Sun,
  UsersRound,
  X,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, type Agent, type AuditEvent, type Project, type Task, type WorkflowDefinition } from './api'
import ApprovalsView from './ApprovalsView'
import MemoryView from './MemoryView'
import AnalyticsView from './AnalyticsView'
import { NotificationCenter } from './components/NotificationCenter'
import SettingsView from './SettingsView'
import BrowserWallView from './BrowserWallView'
import TaskTimelineView, { CancelControls } from './TaskTimelineView'
import AgentCenterView from './AgentCenterView'
import { formatDateTime, formatNumber } from './format'
import ProjectBuilderView from './ProjectBuilderView'
import OpsView from './OpsView'
import { ManagerPlanPanel } from './components/ManagerPlanPanel'
import { AgentControls } from './components/AgentControls'
import { CheckpointPanel } from './components/CheckpointPanel'
import { PullRequestPlans } from './components/PullRequestPlans'
import TaskWorkspaceDiff from './components/TaskWorkspaceDiff'
import WorkspacePanel from './components/WorkspacePanel'
import ProvidersView from './ProvidersView'

type View = 'dashboard' | 'ops' | 'projects' | 'builder' | 'agents' | 'center' | 'tasks' | 'memory' | 'analytics' | 'browsers' | 'approvals' | 'providers' | 'settings'

const navigation: { id: View; label: string; icon: typeof Activity }[] = [
  { id: 'dashboard', label: 'dashboard', icon: Activity },
  { id: 'ops', label: 'opsSection', icon: FileSearch },
  { id: 'projects', label: 'projects', icon: FolderKanban },
  { id: 'builder', label: 'builderSection', icon: Sparkles },
  { id: 'agents', label: 'agents', icon: UsersRound },
  { id: 'center', label: 'agentCenterSection', icon: Gauge },
  { id: 'tasks', label: 'tasks', icon: ListTodo },
  { id: 'memory', label: 'memorySection', icon: BookOpen },
  { id: 'analytics', label: 'analyticsSection', icon: BarChart3 },
  { id: 'browsers', label: 'browserWallSection', icon: MonitorSmartphone },
  { id: 'approvals', label: 'approvalSection', icon: ShieldCheck },
  { id: 'providers', label: 'providerSection', icon: PlugZap },
  { id: 'settings', label: 'settingsSection', icon: Settings },
]

const roleTranslationById: Record<string, string> = {
  'backend-developer': 'roleBackendDeveloper',
  'frontend-developer': 'roleFrontendDeveloper',
  'database-engineer': 'roleDatabaseEngineer',
  'qa-engineer': 'roleQaEngineer',
  'security-engineer': 'roleSecurityEngineer',
  'devops-engineer': 'roleDevopsEngineer',
  'software-architect': 'roleSoftwareArchitect',
  'code-reviewer': 'roleCodeReviewer',
  'documentation-writer': 'roleDocumentationWriter',
  'performance-engineer': 'rolePerformanceEngineer',
  'api-integration-engineer': 'roleApiIntegrationEngineer',
  'ui-ux-developer': 'roleUiUxDeveloper',
  'testing-specialist': 'roleTestingSpecialist',
  'debugging-specialist': 'roleDebuggingSpecialist',
  'research-agent': 'roleResearchAgent',
  'automation-engineer': 'roleAutomationEngineer',
  'infrastructure-engineer': 'roleInfrastructureEngineer',
  'refactoring-specialist': 'roleRefactoringSpecialist',
  'technical-analyst': 'roleTechnicalAnalyst',
  'general-development-agent': 'roleGeneralDevelopmentAgent',
}
const roleTranslationByName: Record<string, string> = {
  'Backend Developer': 'roleBackendDeveloper',
  'Frontend Developer': 'roleFrontendDeveloper',
  'Database Engineer': 'roleDatabaseEngineer',
  'QA Engineer': 'roleQaEngineer',
  'Security Engineer': 'roleSecurityEngineer',
  'DevOps Engineer': 'roleDevopsEngineer',
  'Software Architect': 'roleSoftwareArchitect',
  'Code Reviewer': 'roleCodeReviewer',
  'Documentation Writer': 'roleDocumentationWriter',
  'Performance Engineer': 'rolePerformanceEngineer',
  'API Integration Engineer': 'roleApiIntegrationEngineer',
  'UI/UX Developer': 'roleUiUxDeveloper',
  'Testing Specialist': 'roleTestingSpecialist',
  'Debugging Specialist': 'roleDebuggingSpecialist',
  'Research Agent': 'roleResearchAgent',
  'Automation Engineer': 'roleAutomationEngineer',
  'Infrastructure Engineer': 'roleInfrastructureEngineer',
  'Refactoring Specialist': 'roleRefactoringSpecialist',
  'Technical Analyst': 'roleTechnicalAnalyst',
  'General Development Agent': 'roleGeneralDevelopmentAgent',
}

function readTheme(): 'dark' | 'light' {
  return localStorage.getItem('aatm.theme') === 'light' ? 'light' : 'dark'
}

function formatDate(date: string, language: string): string {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(date) ? date : `${date}Z`
  return formatDateTime(normalized, language)
}

function count(value: number, language: string): string {
  return formatNumber(value, language)
}

function App() {
  const { t, i18n } = useTranslation()
  const [view, setView] = useState<View>('dashboard')
  const [theme, setTheme] = useState<'dark' | 'light'>(readTheme)
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 15_000 })

  useEffect(() => {
    const direction = i18n.dir(i18n.language)
    document.documentElement.lang = i18n.language
    document.documentElement.dir = direction
    document.documentElement.dataset.theme = theme
    localStorage.setItem('aatm.theme', theme)
  }, [i18n.language, theme])

  const changeLanguage = (language: string) => {
    localStorage.setItem('aatm.language', language)
    void i18n.changeLanguage(language)
  }

  const toggleTheme = () => setTheme((current) => current === 'dark' ? 'light' : 'dark')

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true"><Command size={20} strokeWidth={2.4} /></div>
          <div className="brand-copy">
            <span className="brand-name">{t('brand')}</span>
            <span className="brand-subtitle">{t('brandLong')}</span>
          </div>
        </div>

        <div className="workspace-switcher">
          <span className="workspace-glyph"><Bot size={17} /></span>
          <span className="workspace-label">{t('localWorkspace')}</span>
          <span className="workspace-dot" aria-label={health.data ? t('connected') : t('disconnected')} />
        </div>

        <div className="nav-caption">{t('overview')}</div>
        <nav className="primary-nav" aria-label={t('workspace')}>
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              className={`nav-item ${view === id ? 'active' : ''}`}
              type="button"
              key={id}
              onClick={() => setView(id)}
              aria-current={view === id ? 'page' : undefined}
            >
              <Icon size={18} strokeWidth={1.9} />
              <span>{t(label)}</span>
              {id === 'dashboard' && <span className="nav-active-mark" />}
            </button>
          ))}
        </nav>

        <div className="sidebar-spacer" />
        <div className="sidebar-foundation">
          <span className="foundation-icon"><CircleDot size={16} /></span>
          <div>
            <strong>{t('coreOnly')}</strong>
            <p>{t('moreComing')}</p>
          </div>
        </div>
        <div className="sidebar-footer">
          <span className="connection-indicator"><span className={`status-dot ${health.data ? 'online' : health.isLoading ? 'checking' : 'offline'}`} />
            {health.data ? t('connected') : health.isLoading ? t('loading') : t('disconnected')}
          </span>
          <span className="version-label">v0.1.0 · {t('coreOnly')}</span>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <div className="topbar-context">
            <span className="context-product">{t('commandCenter')}</span>
            <span className="context-divider">/</span>
            <span className="context-current">{t(view)}</span>
          </div>
          <div className="topbar-actions">
            <NotificationCenter onNavigate={(target) => setView(target as View)} />
            <div className="api-pill" title={health.data?.database === 'ok' ? t('databaseOnline') : t('disconnected')}>
              <span className={`status-dot ${health.data ? 'online' : health.isLoading ? 'checking' : 'offline'}`} />
              <span>{health.data ? t('connected') : t('disconnected')}</span>
            </div>
            <label className="language-select" aria-label={t('language')}>
              <Languages size={16} />
              <select value={i18n.language} onChange={(event) => changeLanguage(event.target.value)}>
                <option value="en">EN</option>
                <option value="ar">العربية</option>
                <option value="fa">فارسی</option>
              </select>
            </label>
            <button className="icon-button" type="button" onClick={toggleTheme} aria-label={theme === 'dark' ? t('lightMode') : t('darkMode')} title={theme === 'dark' ? t('lightMode') : t('darkMode')}>
              {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </header>

        <div className="page-content">
          {view === 'dashboard' && <DashboardView onNavigate={setView} />}
          {view === 'ops' && <OpsView />}
          {view === 'projects' && <ProjectsView />}
          {view === 'builder' && <ProjectBuilderView />}
          {view === 'agents' && <AgentsView />}
          {view === 'center' && <AgentCenterView />}
          {view === 'tasks' && <TasksView />}
          {view === 'memory' && <MemoryView />}
          {view === 'analytics' && <AnalyticsView />}
          {view === 'browsers' && <BrowserWallView />}
          {view === 'approvals' && <ApprovalsView />}
          {view === 'providers' && <ProvidersView />}
          {view === 'settings' && <SettingsView onTheme={setTheme} onLanguage={(language) => changeLanguage(language)} />}
        </div>
      </main>
    </div>
  )
}

function PageHeading({ title, subtitle, children }: { title: string; subtitle: string; children?: ReactNode }) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow"><span className="eyebrow-line" /> AATM <span> / </span> {title}</div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {children && <div className="heading-actions">{children}</div>}
    </div>
  )
}

function DashboardView({ onNavigate }: { onNavigate: (view: View) => void }) {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const dashboard = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard, refetchInterval: 15_000 })
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 15_000 })

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      queryClient.invalidateQueries({ queryKey: ['health'] }),
    ])
  }

  if (dashboard.isLoading) {
    return <StatePanel icon={<LoaderCircle className="spin" size={22} />} title={t('loading')} />
  }
  if (dashboard.isError || !dashboard.data) {
    return <StatePanel icon={<CircleAlert size={22} />} title={t('loadError')} action={<button className="button button-secondary" type="button" onClick={() => void refresh()}>{t('retry')}</button>} />
  }

  const data = dashboard.data
  const openTasks = (data.tasks.by_state.pending ?? 0) + (data.tasks.by_state.assigned ?? 0) + (data.tasks.by_state.waiting ?? 0)

  return (
    <>
      <PageHeading title={t('dashboard')} subtitle={t('welcomeDetail')}>
        <span className="live-pill"><span className="live-pulse" />{t('liveData')}</span>
      </PageHeading>
      <ManagerPlanPanel />
      <section className="welcome-row">
        <div>
          <div className="welcome-kicker">{t('commandCenter')}</div>
          <h2>{t('welcome')}</h2>
          <p>{t('foundationsNote')}</p>
        </div>
        <div className="welcome-orbit" aria-hidden="true">
          <div className="orbit-ring orbit-ring-one" />
          <div className="orbit-ring orbit-ring-two" />
          <div className="orbit-core"><Command size={25} /></div>
          <span className="orbit-node node-one" />
          <span className="orbit-node node-two" />
          <span className="orbit-node node-three" />
        </div>
      </section>

      <section className="metric-grid" aria-label={t('dashboard')}>
        <MetricCard
          icon={<FolderKanban size={18} />}
          label={t('projectsTracked')}
          value={count(data.projects.total, i18n.language)}
          caption={t('projectsTitle')}
          tone="blue"
          onClick={() => onNavigate('projects')}
        />
        <MetricCard
          icon={<UsersRound size={18} />}
          label={t('registeredAgents')}
          value={count(data.agents.total, i18n.language)}
          caption={t('workersConfigured', { count: data.agents.workers, max: data.agents.max_workers })}
          tone="violet"
          onClick={() => onNavigate('agents')}
        />
        <MetricCard
          icon={<ListTodo size={18} />}
          label={t('tasksTracked')}
          value={count(data.tasks.total, i18n.language)}
          caption={t('taskQueue')}
          tone="cyan"
          onClick={() => onNavigate('tasks')}
        />
        <MetricCard
          icon={<Clock3 size={18} />}
          label={t('taskQueue')}
          value={count(openTasks, i18n.language)}
          caption={t('queueSummary', { total: count(openTasks, i18n.language) })}
          tone="amber"
          onClick={() => onNavigate('tasks')}
        />
      </section>

      <section className="content-grid">
        <div className="panel activity-panel">
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">{t('systemReady')}</span>
              <h3>{t('recentActivity')}</h3>
            </div>
            <span className="panel-icon"><Activity size={17} /></span>
          </div>
          {data.recent_events.length === 0 ? (
            <div className="empty-inline"><span className="empty-symbol"><Activity size={18} /></span><p>{t('noActivity')}</p></div>
          ) : (
            <div className="activity-list">
              {data.recent_events.map((event) => <ActivityRow key={event.id} event={event} />)}
            </div>
          )}
        </div>
        <div className="panel system-panel">
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">{t('localWorkspace')}</span>
              <h3>{t('systemReady')}</h3>
            </div>
            <span className="panel-icon panel-icon-green"><Check size={17} /></span>
          </div>
          <div className="system-state-row">
            <span className={`status-dot ${health.data ? 'online' : health.isLoading ? 'checking' : 'offline'}`} />
            <div><strong>{health.data ? t('connected') : t('disconnected')}</strong><span>{health.data ? t('databaseOnline') : t('loadError')}</span></div>
          </div>
          <div className="system-divider" />
          <div className="manager-alert">
            <div className="manager-alert-icon"><Bot size={18} /></div>
            <div><strong>{t('managerUnconfigured')}</strong><p>{t('managerUnconfiguredDetail')}</p></div>
          </div>
          <div className="foundation-footer"><span className="foundation-dot" />{t('coreOnly')}</div>
        </div>
      </section>
    </>
  )
}

function MetricCard({ icon, label, value, caption, tone, onClick }: { icon: ReactNode; label: string; value: string; caption: string; tone: string; onClick: () => void }) {
  return (
    <button type="button" className="metric-card" onClick={onClick}>
      <div className="metric-top"><span className={`metric-icon ${tone}`}>{icon}</span><ArrowDownLeft size={15} className="metric-arrow" /></div>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      <span className="metric-caption">{caption}</span>
    </button>
  )
}

function ActivityRow({ event }: { event: AuditEvent }) {
  const { t, i18n } = useTranslation()
  const eventLabels: Record<string, string> = {
    'system.manager_initialized': t('managerUnconfigured'),
    'project.created': t('projectCreated'),
    'agent.registered': t('agentRegistered'),
    'task.created': t('taskCreated'),
    'task.assignment_changed': t('taskAssigned'),
    'task.state_changed': t('taskStateChanged'),
    'provider.config_updated': t('providerConfigUpdated'),
    'providers.settings_updated': t('providerSettingsUpdated'),
    'budget.limit_updated': t('budgetLimitUpdated'),
  }
  const entityLabels: Record<string, string> = {
    system: t('entitySystem'),
    project: t('entityProject'),
    agent: t('entityAgent'),
    task: t('entityTask'),
  }
  return (
    <div className="activity-row">
      <span className="activity-marker"><span /></span>
      <div className="activity-copy"><strong>{eventLabels[event.event_type] ?? event.event_type}</strong><span>{entityLabels[event.entity_type] ?? t('entityRecord')}</span></div>
      <time>{formatDate(event.created_at, i18n.language)}</time>
    </div>
  )
}

function ProjectsView() {
  const { t } = useTranslation()
  const [formOpen, setFormOpen] = useState(false)
  const queryClient = useQueryClient()
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects })
  const [selectedProject, setSelectedProject] = useState<string>('')
  const mutation = useMutation({
    mutationFn: api.createProject,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['projects'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ])
      setFormOpen(false)
    },
  })

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const name = String(form.get('name') ?? '').trim()
    if (!name) return
    mutation.mutate({ name, description: String(form.get('description') ?? '').trim() })
  }

  return (
    <>
      <PageHeading title={t('projectsTitle')} subtitle={t('projectsSubtitle')}>
        <button className="button button-primary" type="button" onClick={() => setFormOpen((open) => !open)}><Plus size={16} />{t('newProject')}</button>
      </PageHeading>
      {formOpen && <FormPanel title={t('newProject')} onClose={() => setFormOpen(false)}>
        <form className="form-grid" onSubmit={submit}>
          <label className="field"><span>{t('projectName')}</span><input name="name" required maxLength={160} autoFocus /></label>
          <label className="field"><span>{t('description')}</span><textarea name="description" rows={3} maxLength={10_000} /></label>
          {mutation.isError && <p className="form-error">{t('requestFailed')}</p>}
          <div className="form-actions"><button className="button button-secondary" type="button" onClick={() => setFormOpen(false)}>{t('cancel')}</button><button className="button button-primary" type="submit" disabled={mutation.isPending}>{mutation.isPending ? t('creating') : t('create')}</button></div>
        </form>
      </FormPanel>}
      {projects.isLoading ? <StatePanel icon={<LoaderCircle className="spin" size={22} />} title={t('loading')} /> : projects.isError ? <StatePanel icon={<CircleAlert size={22} />} title={t('loadError')} /> : (
        <div className="record-grid">
          {projects.data?.length ? projects.data.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onSelect={() => setSelectedProject((current) => (current === project.id ? '' : project.id))}
              selected={selectedProject === project.id}
            />
          )) : <EmptyCard title={t('noProjects')} description={t('noProjectsDetail')} icon={<FolderKanban size={22} />} />}
        </div>
      )}
      {selectedProject ? (
        <>
          <WorkspacePanel
            projectId={selectedProject}
            projectName={projects.data?.find((item) => item.id === selectedProject)?.name ?? ''}
          />
          <PullRequestPlans projectId={selectedProject} />
        </>
      ) : projects.data?.length ? (
        <p className="form-note">{t('workspaceSelect')}</p>
      ) : null}
    </>
  )
}

function ProjectCard({ project, onSelect, selected }: { project: Project; onSelect: () => void; selected: boolean }) {
  const { t, i18n } = useTranslation()
  return (
    <article className={`record-card ${selected ? 'record-card-selected' : ''}`}>
      <div className="record-card-top"><span className="record-icon blue"><FolderKanban size={18} /></span><span className="status-chip"><span className="status-dot online" />{project.status === 'active' ? t('statusActive') : project.status}</span></div>
      <h3>{project.name}</h3>
      <p className="record-description">{project.description || t('noDescription')}</p>
      <div className="record-meta"><span>{t('createdAt', { date: formatDate(project.created_at, i18n.language) })}</span></div>
      <div className="form-actions record-actions">
        <button className="button button-secondary task-action-button" type="button" onClick={onSelect}>
          <FolderGit2 size={12} />{t('workspaceSection')}
        </button>
      </div>
    </article>
  )
}

function AgentsView() {
  const { t } = useTranslation()
  const [formOpen, setFormOpen] = useState(false)
  const queryClient = useQueryClient()
  const agents = useQuery({ queryKey: ['agents'], queryFn: api.agents })
  const roles = useQuery({ queryKey: ['agent-roles'], queryFn: api.agentRoles })
  const mutation = useMutation({
    mutationFn: api.createAgent,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['agents'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ])
      setFormOpen(false)
    },
  })

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const name = String(form.get('name') ?? '').trim()
    const role = String(form.get('role') ?? '').trim()
    if (!name || !role) return
    mutation.mutate({ name, role, description: String(form.get('description') ?? '').trim() })
  }

  return (
    <>
      <PageHeading title={t('agentsTitle')} subtitle={t('agentsSubtitle')}>
        <button className="button button-primary" type="button" onClick={() => setFormOpen((open) => !open)}><Plus size={16} />{t('newAgent')}</button>
      </PageHeading>
      {formOpen && <FormPanel title={t('newAgent')} onClose={() => setFormOpen(false)}>
        <form className="form-grid two-columns" onSubmit={submit}>
          <label className="field"><span>{t('name')}</span><input name="name" required maxLength={120} autoFocus /></label>
          <label className="field"><span>{t('role')}</span><select name="role" required defaultValue=""><option value="" disabled>{t('chooseRole')}</option>{roles.data?.map((role) => <option key={role.id} value={role.name}>{t(roleTranslationById[role.id] ?? role.name)}</option>)}</select></label>
          <label className="field field-full"><span>{t('description')}</span><textarea name="description" rows={2} maxLength={10_000} /></label>
          <p className="form-note field-full">{t('foundationsNote')}</p>
          {mutation.isError && <p className="form-error field-full">{t('requestFailed')}</p>}
          <div className="form-actions field-full"><button className="button button-secondary" type="button" onClick={() => setFormOpen(false)}>{t('cancel')}</button><button className="button button-primary" type="submit" disabled={mutation.isPending || roles.isLoading}>{mutation.isPending ? t('creating') : t('create')}</button></div>
        </form>
      </FormPanel>}
      {agents.isLoading ? <StatePanel icon={<LoaderCircle className="spin" size={22} />} title={t('loading')} /> : agents.isError ? <StatePanel icon={<CircleAlert size={22} />} title={t('loadError')} /> : (
        <div className="record-grid">
          {agents.data?.length ? agents.data.map((agent) => <AgentCard key={agent.id} agent={agent} />) : <EmptyCard title={t('noAgents')} description={t('noAgentsDetail')} icon={<UsersRound size={22} />} />}
        </div>
      )}
    </>
  )
}

function AgentCard({ agent }: { agent: Agent }) {
  const { t } = useTranslation()
  const agentStatusKey: Record<string, string> = { idle: 'statusIdle', active: 'statusActiveAgent', paused: 'statusPaused', running: 'statusRunning', error: 'statusError', disabled: 'statusDisabled', offline: 'statusOffline' }
  return (
    <article className={`record-card agent-card ${agent.is_manager ? 'manager-card' : ''}`}>
      <div className="record-card-top"><span className={`record-icon ${agent.is_manager ? 'violet' : 'cyan'}`}><Bot size={18} /></span><span className="status-chip"><span className={`status-dot ${agent.status === 'idle' ? 'online' : 'checking'}`} />{t(agentStatusKey[agent.status] ?? agent.status)}</span></div>
      <div className="agent-name-row"><h3>{agent.is_manager ? t('manager') : agent.name}</h3>{agent.is_manager && <span className="manager-tag">{t('manager')}</span>}</div>
      <AgentControls agent={agent} />
      <p className="agent-role">{agent.is_manager ? t('managerAgentRole') : t(roleTranslationByName[agent.role] ?? agent.role)}</p>
      <p className="record-description">{agent.is_manager ? t('managerUnconfiguredDetail') : agent.description || t('noAgentsDetail')}</p>
      <div className="record-meta"><span>{t('provider')}: {agent.provider === 'unconfigured' ? t('unconfigured') : agent.provider}</span><span>{t('status')}: {agent.status === 'idle' ? t('statusIdle') : agent.status}</span></div>
    </article>
  )
}

function TasksView() {
  const { t, i18n } = useTranslation()
  const [formOpen, setFormOpen] = useState(false)
  const queryClient = useQueryClient()
  const tasks = useQuery({ queryKey: ['tasks'], queryFn: api.tasks })
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects })
  const agents = useQuery({ queryKey: ['agents'], queryFn: api.agents })
  const workflow = useQuery({ queryKey: ['workflow'], queryFn: api.workflow })
  const ready = useQuery({ queryKey: ['readyTasks'], queryFn: api.readyTasks })
  const mutation = useMutation({
    mutationFn: api.createTask,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ])
      setFormOpen(false)
    },
  })

  const workers = useMemo(() => agents.data?.filter((agent) => !agent.is_manager) ?? [], [agents.data])
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const title = String(form.get('title') ?? '').trim()
    if (!title) return
    const projectId = String(form.get('project_id') ?? '')
    const agentId = String(form.get('assigned_agent_id') ?? '')
    mutation.mutate({
      title,
      description: String(form.get('description') ?? '').trim(),
      project_id: projectId || null,
      assigned_agent_id: agentId || null,
      priority: String(form.get('priority') ?? 'normal') as Task['priority'],
    })
  }

  return (
    <>
      <PageHeading title={t('tasksTitle')} subtitle={t('tasksSubtitle')}>
        <button className="button button-primary" type="button" onClick={() => setFormOpen((open) => !open)}><Plus size={16} />{t('newTask')}</button>
      </PageHeading>
      {formOpen && <FormPanel title={t('newTask')} onClose={() => setFormOpen(false)}>
        <form className="form-grid two-columns" onSubmit={submit}>
          <label className="field field-full"><span>{t('taskTitle')}</span><input name="title" required maxLength={200} autoFocus /></label>
          <label className="field"><span>{t('project')}</span><select name="project_id" defaultValue=""><option value="">{t('noProject')}</option>{projects.data?.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}</select></label>
          <label className="field"><span>{t('assignee')}</span><select name="assigned_agent_id" defaultValue=""><option value="">{t('noAssignee')}</option>{workers.map((agent) => <option value={agent.id} key={agent.id}>{agent.name} · {agent.role}</option>)}</select></label>
          <label className="field"><span>{t('priority')}</span><select name="priority" defaultValue="normal"><option value="low">{t('priorityLow')}</option><option value="normal">{t('priorityNormal')}</option><option value="high">{t('priorityHigh')}</option><option value="urgent">{t('priorityUrgent')}</option></select></label>
          <label className="field field-full"><span>{t('description')}</span><textarea name="description" rows={3} maxLength={20_000} /></label>
          {mutation.isError && <p className="form-error field-full">{t('requestFailed')}</p>}
          <div className="form-actions field-full"><button className="button button-secondary" type="button" onClick={() => setFormOpen(false)}>{t('cancel')}</button><button className="button button-primary" type="submit" disabled={mutation.isPending}>{mutation.isPending ? t('creating') : t('create')}</button></div>
        </form>
      </FormPanel>}
      <div className="notice-panel"><ListTodo size={17} /><p>{t('workflowNote')}</p><span className="notice-count">{t('readyQueue')}: {ready.data?.tasks.length ?? 0}</span></div>
      <OrchestratorPanel />
      {tasks.isLoading ? <StatePanel icon={<LoaderCircle className="spin" size={22} />} title={t('loading')} /> : tasks.isError ? <StatePanel icon={<CircleAlert size={22} />} title={t('loadError')} /> : (
        <div className="panel task-table-panel">
          <div className="panel-heading"><div><span className="panel-kicker">{t('liveData')}</span><h3>{t('workflowTitle')}</h3></div><span className="panel-icon"><ListTodo size={17} /></span></div>
          {tasks.data?.length ? <div className="task-list">
            {tasks.data.map((task) => <TaskRow key={task.id} task={task} projects={projects.data ?? []} agents={agents.data ?? []} language={i18n.language} workflow={workflow.data} />)}
          </div> : <EmptyCard title={t('noTasks')} description={t('noTasksDetail')} icon={<ListTodo size={22} />} />}
        </div>
      )}
    </>
  )
}

function ReviewForm({ task, agents }: { task: Task; agents: Agent[] }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [reviewer, setReviewer] = useState('')
  const [verdict, setVerdict] = useState<'approved' | 'rework_required'>('approved')
  const [summary, setSummary] = useState('')
  const [checks, setChecks] = useState('')
  const reviews = useQuery({
    queryKey: ['reviews', task.id],
    queryFn: () => api.taskReviews(task.id),
    enabled: open,
  })
  const mutation = useMutation({
    mutationFn: () => api.createReview(task.id, {
      reviewer_agent_id: reviewer,
      verdict,
      summary,
      checks: checks.split('\n').map((line) => line.trim()).filter(Boolean)
        .map((line) => ({ check: line, result: 'pass' })),
      idempotency_key: crypto.randomUUID(),
    }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['reviews', task.id] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
      ])
    },
  })

  const reviewable = task.state === 'reviewing' || task.state === 'completed'
  if (!reviewable) return null
  const candidates = agents.filter((agent) => !agent.is_manager && agent.id !== task.assigned_agent_id)

  return (
    <div className="review-block">
      <button className="button button-secondary task-action-button" type="button" onClick={() => setOpen((value) => !value)}>
        <ShieldCheck size={12} />{open ? t('reviewClose') : t('reviewOpen')}
      </button>
      {open && (
        <form
          className="review-form"
          onSubmit={(event) => {
            event.preventDefault()
            if (!reviewer) return
            mutation.mutate()
          }}
        >
          <label className="field">
            <span>{t('reviewReviewer')}</span>
            <select value={reviewer} onChange={(event) => setReviewer(event.target.value)} required>
              <option value="">{t('reviewSelectReviewer')}</option>
              {candidates.map((agent) => <option key={agent.id} value={agent.id}>{agent.name} · {agent.role}</option>)}
            </select>
          </label>
          <label className="field">
            <span>{t('reviewVerdict')}</span>
            <select value={verdict} onChange={(event) => setVerdict(event.target.value as 'approved' | 'rework_required')}>
              <option value="approved">{t('stateApproved')}</option>
              <option value="rework_required">{t('stateRework')}</option>
            </select>
          </label>
          <label className="field field-full">
            <span>{t('reviewChecks')}</span>
            <textarea rows={3} value={checks} onChange={(event) => setChecks(event.target.value)} placeholder={t('reviewChecksHint')} />
          </label>
          <label className="field field-full">
            <span>{t('reviewSummary')}</span>
            <input value={summary} maxLength={500} onChange={(event) => setSummary(event.target.value)} />
          </label>
          <div className="form-actions field-full">
            <button className="button button-primary" type="submit" disabled={mutation.isPending || !reviewer}>
              {mutation.isPending ? t('reviewSubmitting') : t('reviewSubmit')}
            </button>
          </div>
          {mutation.isError && <p className="form-error field-full">{t('requestFailed')}: {mutation.error.message}</p>}
          {mutation.isSuccess && <p className="form-success field-full"><Check size={13} />{t('reviewRecorded')} · {mutation.data.task_state}</p>}
        </form>
      )}
      {open && reviews.data?.reviews.length ? (
        <ul className="review-history">
          {reviews.data.reviews.map((item) => (
            <li key={item.id}>
              <span className={`state-badge ${item.verdict}`}>{item.verdict === 'approved' ? t('stateApproved') : t('stateRework')}</span>
              <span>{item.summary || t('reviewNoSummary')}</span>
              <span className="review-checks">{item.checks.length} {t('reviewCheckCount')}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

function OrchestratorPanel() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const status = useQuery({ queryKey: ['orchestrator'], queryFn: api.orchestratorStatus })
  const recovery = useMutation({
    mutationFn: api.recoverLeases,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['orchestrator'] }),
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['readyTasks'] }),
      ])
    },
  })

  return (
    <section className="panel orchestrator-panel">
      <div className="panel-heading">
        <div><span className="panel-kicker">{t('providerLiveCallsOff')}</span><h3>{t('orchestratorTitle')}</h3></div>
        <span className="panel-icon"><Cpu size={17} /></span>
      </div>
      <p className="panel-note">{t('orchestratorNote')}</p>
      {status.isLoading ? <p className="form-note">{t('loading')}</p> : status.isError || !status.data ? <p className="form-error">{t('loadError')}</p> : (
        <>
          <div className="orchestrator-counts">
            <div className="orchestrator-count"><span>{t('orchestratorRunning')}</span><strong>{status.data.counts.running}</strong></div>
            <div className="orchestrator-count"><span>{t('orchestratorWaiting')}</span><strong>{status.data.counts.waiting_for_retry}</strong></div>
            <div className={`orchestrator-count ${status.data.counts.expired_leases ? 'attention' : ''}`}><span>{t('orchestratorExpired')}</span><strong>{status.data.counts.expired_leases}</strong></div>
            <div className="orchestrator-count"><span>{t('orchestratorAssigned')}</span><strong>{status.data.counts.assigned}</strong></div>
          </div>
          <ul className="orchestrator-leases">
            {status.data.leases.map((lease) => (
              <li key={lease.task_id}>
                <span>{lease.title}</span>
                <span>{lease.lease_owner ?? t('orchestratorNoOwner')}</span>
                <span className={lease.lease_expired ? 'lease-expired' : ''}>{lease.lease_expired ? t('orchestratorLeaseExpired') : t('orchestratorLeaseActive')}</span>
              </li>
            ))}
            {!status.data.leases.length && <li className="form-note">{t('orchestratorNoLeases')}</li>}
          </ul>
          <div className="form-actions">
            <button className="button button-secondary" type="button" disabled={recovery.isPending || !status.data.counts.expired_leases} onClick={() => recovery.mutate()}>{t('orchestratorRecover')}</button>
          </div>
          {recovery.isSuccess && <p className="form-success"><Check size={13} />{t('orchestratorRecovered')}: {recovery.data.count}</p>}
          {recovery.isError && <p className="form-error">{t('requestFailed')}: {recovery.error.message}</p>}
          <p className="form-note">{status.data.executor.reason}</p>
          <ResourceSummary />
        </>
      )}
    </section>
  )
}

function ResourceSummary() {
  const { t } = useTranslation()
  const resources = useQuery({ queryKey: ['resources'], queryFn: () => api.resources(2), refetchInterval: 15000 })
  if (resources.isLoading || !resources.data) return null
  const { snapshot, recommendation } = resources.data
  const memory = snapshot.memory_used_ratio
  const disk = snapshot.disk_used_ratio
  return (
    <div className="resource-summary">
      <div className="system-divider" />
      <span className="panel-kicker">{t('resourcesTitle')}</span>
      <div className="orchestrator-counts">
        <div className="orchestrator-count"><span>{t('resourceCpu')}</span><strong>{snapshot.cpu_percent !== null ? `${Math.round(snapshot.cpu_percent)}%` : '—'}</strong></div>
        <div className={`orchestrator-count ${memory !== null && memory >= 0.9 ? 'attention' : ''}`}><span>{t('resourceMemory')}</span><strong>{memory !== null ? `${Math.round(memory * 100)}%` : '—'}</strong></div>
        <div className={`orchestrator-count ${disk !== null && disk >= 0.95 ? 'attention' : ''}`}><span>{t('resourceDisk')}</span><strong>{disk !== null ? `${Math.round(disk * 100)}%` : '—'}</strong></div>
        <div className="orchestrator-count"><span>{t('resourceRecommended')}</span><strong>{recommendation.recommended_concurrency}</strong></div>
      </div>
      <p className="form-note">{recommendation.note}</p>
    </div>
  )
}

function TaskRow({ task, projects, agents, language, workflow }: { task: Task; projects: Project[]; agents: Agent[]; language: string; workflow?: WorkflowDefinition }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [note, setNote] = useState('')
  const project = projects.find((item) => item.id === task.project_id)
  const agent = agents.find((item) => item.id === task.assigned_agent_id)
  const stateKey: Record<string, string> = {
    pending: 'statePending', assigned: 'stateAssigned', running: 'stateRunning', waiting: 'stateWaiting',
    completed: 'stateCompleted', failed: 'stateFailed', reviewing: 'stateReviewing',
    rework_required: 'stateRework', approved: 'stateApproved', cancelled: 'stateCancelled',
  }
  const priorityKey: Record<string, string> = { low: 'priorityLow', normal: 'priorityNormal', high: 'priorityHigh', urgent: 'priorityUrgent' }
  const nextStates = workflow?.transitions[task.state] ?? []
  const mutation = useMutation({
    mutationFn: (targetState: string) => api.changeTaskState(task.id, {
      target_state: targetState,
      idempotency_key: crypto.randomUUID(),
      note,
    }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['readyTasks'] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
      ])
      setNote('')
    },
  })
  return (
    <article className="task-row task-row-extended">
      <div className="task-leading"><span className={`task-state-icon ${task.state}`}><CircleDot size={16} /></span><div><h4>{task.title}</h4><p>{task.description || t('tasksSubtitle')}</p></div></div>
      <div className="task-badges"><span className={`priority-badge ${task.priority}`}>{t(priorityKey[task.priority] ?? 'priorityNormal')}</span><span className={`state-badge ${task.state}`}>{t(stateKey[task.state] ?? 'statePending')}</span></div>
      <div className="task-secondary"><span>{project?.name ?? t('noProject')}</span><span>{agent?.name ?? t('noAssignee')}</span><span>{t('transitionRetryCount')}: {task.retry_count}</span><time>{formatDate(task.created_at, language)}</time></div>
      <div className="task-actions">
        <ReviewForm task={task} agents={agents} />
        <CheckpointPanel task={task} />
        {task.project_id && <TaskWorkspaceDiff projectId={task.project_id} taskId={task.id} />}
        <CancelControls task={task} />
        <TaskTimelineView taskId={task.id} language={language} />
        {nextStates.length ? (
          <>
            <label className="task-note-field">
              <span className="visually-hidden">{t('transitionNote')}</span>
              <input value={note} maxLength={2000} placeholder={t('transitionNote')} onChange={(event) => setNote(event.target.value)} />
            </label>
            <div className="task-action-buttons">
              {nextStates.map((target) => (
                <button
                  key={target}
                  className="button button-secondary task-action-button"
                  type="button"
                  disabled={mutation.isPending}
                  onClick={() => mutation.mutate(target)}
                >
                  {t(stateKey[target] ?? target)} <ArrowRight size={12} />
                </button>
              ))}
            </div>
            {mutation.isPending && <p className="form-note">{t('transitionApplying')}</p>}
            {mutation.isSuccess && <p className="form-success">{t(mutation.data?.transition_created ? 'transitionUpdated' : 'transitionReplay')}</p>}
            {mutation.isError && <p className="form-error">{t('requestFailed')}: {mutation.error.message}</p>}
          </>
        ) : <p className="form-note">{t('workflowNote')}</p>}
      </div>
    </article>
  )
}

function FormPanel({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return <section className="panel form-panel"><div className="form-panel-heading"><h3>{title}</h3><button className="icon-button quiet" type="button" aria-label={title} onClick={onClose}><X size={17} /></button></div>{children}</section>
}

function EmptyCard({ title, description, icon }: { title: string; description: string; icon: ReactNode }) {
  return <div className="empty-card"><span className="empty-card-icon">{icon}</span><h3>{title}</h3><p>{description}</p></div>
}

function StatePanel({ icon, title, action }: { icon: ReactNode; title: string; action?: ReactNode }) {
  return <div className="state-panel"><span>{icon}</span><p>{title}</p>{action}</div>
}

export default App
