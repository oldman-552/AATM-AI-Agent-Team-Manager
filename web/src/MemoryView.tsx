import { FormEvent, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Check, CircleAlert, History, LoaderCircle, Plus, RotateCcw, Search, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, type MemoryScope } from './api'

const scopes: MemoryScope[] = ['project', 'decision', 'agent', 'task', 'global']

const scopeLabel: Record<MemoryScope, string> = {
  global: 'memoryScopeGlobal',
  project: 'memoryScopeProject',
  agent: 'memoryScopeAgent',
  task: 'memoryScopeTask',
  decision: 'memoryScopeDecision',
}

export default function MemoryView() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.projects })
  const [projectId, setProjectId] = useState('')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [form, setForm] = useState({ title: '', content: '', scope: 'project' as MemoryScope, key: '', tags: '' })

  const scope = projectId || null
  const entries = useQuery({
    queryKey: ['memory', scope],
    queryFn: () => api.memory(scope),
  })
  const search = useMutation({ mutationFn: () => api.searchMemory(query.trim(), scope) })
  const detail = useQuery({
    queryKey: ['memoryEntry', expanded, scope],
    queryFn: () => api.memoryEntry(expanded as string, scope),
    enabled: Boolean(expanded),
  })

  const save = useMutation({
    mutationFn: () => api.saveMemory({
      title: form.title.trim(),
      content: form.content.trim(),
      scope: form.scope,
      key: form.key.trim() || null,
      project_id: scope,
      tags: form.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
    }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['memory'] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
      ])
      setForm({ title: '', content: '', scope: 'project', key: '', tags: '' })
      setOpen(false)
    },
  })
  const rollback = useMutation({
    mutationFn: ({ id, version }: { id: string; version: number }) => api.rollbackMemory(id, version, scope),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['memory'] }),
        queryClient.invalidateQueries({ queryKey: ['memoryEntry'] }),
      ])
    },
  })
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteMemory(id, scope),
    onSuccess: async () => {
      setExpanded(null)
      await queryClient.invalidateQueries({ queryKey: ['memory'] })
    },
  })

  const visible = useMemo(() => search.data?.results.map((item) => item.entry) ?? entries.data?.entries ?? [], [search.data, entries.data])

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    save.mutate()
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-line" /> AATM <span> / </span> {t('memoryTitle')}</div>
          <h1>{t('memoryTitle')}</h1>
          <p>{t('memorySubtitle')}</p>
        </div>
        <button className="button button-primary" type="button" onClick={() => setOpen((value) => !value)}>
          <Plus size={16} />{t('memoryNew')}
        </button>
      </div>

      <div className="notice-panel">
        <BookOpen size={17} />
        <p>{t('memoryIsolationNote')}</p>
        <label className="memory-project-select">
          <span>{t('memoryProject')}</span>
          <select value={projectId} onChange={(event) => { setProjectId(event.target.value); setExpanded(null); search.reset() }}>
            <option value="">{t('memoryGlobalOnly')}</option>
            {projects.data?.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </label>
      </div>

      {open && (
        <section className="panel approval-form-panel">
          <form className="form-grid two-columns" onSubmit={submit}>
            <label className="field"><span>{t('memoryEntryTitle')}</span><input required maxLength={200} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
            <label className="field"><span>{t('memoryScope')}</span><select value={form.scope} onChange={(event) => setForm({ ...form, scope: event.target.value as MemoryScope })}>{scopes.map((item) => <option key={item} value={item} disabled={!projectId && item !== 'global'}>{t(scopeLabel[item])}</option>)}</select></label>
            <label className="field"><span>{t('memoryKey')}</span><input maxLength={120} placeholder="db-choice" value={form.key} onChange={(event) => setForm({ ...form, key: event.target.value })} /></label>
            <label className="field"><span>{t('memoryTags')}</span><input maxLength={200} placeholder="architecture, db" value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} /></label>
            <label className="field field-full"><span>{t('memoryContent')}</span><textarea required rows={4} maxLength={20000} value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} /></label>
            {!projectId && form.scope !== 'global' && <p className="form-note field-full">{t('memorySelectProjectFirst')}</p>}
            {save.isError && <p className="form-error field-full">{t('requestFailed')}: {save.error.message}</p>}
            <div className="form-actions field-full">
              <button className="button button-secondary" type="button" onClick={() => setOpen(false)}>{t('cancel')}</button>
              <button className="button button-primary" type="submit" disabled={save.isPending || !form.title.trim() || !form.content.trim()}>
                {save.isPending ? t('creating') : t('memorySave')}
              </button>
            </div>
          </form>
        </section>
      )}

      <form
        className="memory-search"
        onSubmit={(event) => { event.preventDefault(); if (query.trim()) search.mutate() }}
      >
        <Search size={15} />
        <input value={query} maxLength={200} placeholder={t('memorySearchPlaceholder')} onChange={(event) => setQuery(event.target.value)} />
        <button className="button button-secondary" type="submit" disabled={search.isPending || !query.trim()}>
          {search.isPending ? t('loading') : t('memorySearch')}
        </button>
        {search.isSuccess && <button className="button button-secondary" type="button" onClick={() => { search.reset(); setQuery('') }}>{t('memoryClearSearch')}</button>}
      </form>

      {entries.isLoading ? (
        <div className="state-panel"><span><LoaderCircle className="spin" size={22} /></span><p>{t('loading')}</p></div>
      ) : entries.isError ? (
        <div className="state-panel"><span><CircleAlert size={22} /></span><p>{t('loadError')}</p></div>
      ) : visible.length ? (
        <div className="memory-list">
          {visible.map((entry) => (
            <article className="panel memory-card" key={entry.id}>
              <div className="memory-card-top">
                <span className="state-badge">{t(scopeLabel[entry.scope])}</span>
                <span className="memory-version">v{entry.version}</span>
                <h3>{entry.title}</h3>
              </div>
              <p className="memory-content">{entry.content.length > 260 ? `${entry.content.slice(0, 260)}…` : entry.content}</p>
              <div className="memory-card-actions">
                {entry.tags.map((tag) => <span className="memory-tag" key={tag}>{tag}</span>)}
                <button className="button button-secondary task-action-button" type="button" onClick={() => setExpanded(expanded === entry.id ? null : entry.id)}>
                  <History size={12} />{t('memoryHistory')}
                </button>
                <button
                  className="button button-secondary task-action-button"
                  type="button"
                  onClick={() => remove.mutate(entry.id)}
                  disabled={remove.isPending}
                >
                  <Trash2 size={12} />{t('delete')}
                </button>
              </div>
              {expanded === entry.id && (
                <div className="memory-history">
                  {detail.isLoading && <p className="form-note">{t('loading')}</p>}
                  {detail.data?.history.map((item) => (
                    <div className="memory-version-row" key={item.version}>
                      <span>v{item.version}</span>
                      <span className="memory-version-content">{item.content}</span>
                      <button
                        className="button button-secondary task-action-button"
                        type="button"
                        disabled={rollback.isPending || item.version === detail.data?.entry.version}
                        onClick={() => rollback.mutate({ id: entry.id, version: item.version })}
                      >
                        <RotateCcw size={11} />{t('memoryRestore')}
                      </button>
                    </div>
                  ))}
                  {rollback.isSuccess && <p className="form-success"><Check size={13} />{t('memoryRestored')}</p>}
                  {rollback.isError && <p className="form-error">{rollback.error.message}</p>}
                </div>
              )}
            </article>
          ))}
        </div>
      ) : (
        <div className="state-panel"><span><BookOpen size={22} /></span><p>{t('memoryEmpty')}</p></div>
      )}
      {search.data && <p className="form-note">{search.data.retrieval}</p>}
    </>
  )
}
