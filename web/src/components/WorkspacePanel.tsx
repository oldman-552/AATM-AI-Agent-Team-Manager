import { FormEvent, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, CircleAlert, FolderGit2, GitBranch, LoaderCircle, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'

export default function WorkspacePanel({ projectId, projectName }: { projectId: string; projectName: string }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [source, setSource] = useState('')
  const [branch, setBranch] = useState('')
  const workspace = useQuery({
    queryKey: ['workspace', projectId],
    queryFn: () => api.workspace(projectId),
    enabled: Boolean(projectId),
  })

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['workspace', projectId] })
    await queryClient.invalidateQueries({ queryKey: ['events'] })
  }

  const create = useMutation({
    mutationFn: () => api.createWorkspace(projectId, {
      local_source: source.trim() || null,
      branch: branch.trim() || null,
    }),
    onSuccess: async () => {
      await invalidate()
      setCreating(false)
      setSource('')
      setBranch('')
    },
  })
  const newBranch = useMutation({
    mutationFn: (name: string) => api.createWorkspaceBranch(projectId, name),
    onSuccess: invalidate,
  })
  const remove = useMutation({ mutationFn: () => api.removeWorkspace(projectId), onSuccess: invalidate })

  const data = workspace.data
  const status = data?.status

  return (
    <section className="panel workspace-panel">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">{t('workspaceSection')} · {projectName}</span>
          <h3>{t('workspaceTitle')}</h3>
        </div>
        <span className="panel-icon"><FolderGit2 size={17} /></span>
      </div>
      <p className="panel-note">{t('workspaceSubtitle')}</p>

      {workspace.isLoading ? (
        <p className="form-note">{t('loading')}</p>
      ) : workspace.isError ? (
        <p className="form-error">{t('loadError')}</p>
      ) : data?.workspace ? (
        <>
          <div className="workspace-meta">
            <div><span>{t('workspaceBranch')}</span><strong><GitBranch size={12} />{data.workspace.branch ?? '—'}</strong></div>
            <div><span>{t('workspaceClean')}</span><strong className={status && !status.clean ? 'workspace-dirty' : ''}>{status?.clean ? t('workspaceClean') : t('workspaceDirty')}</strong></div>
            <div><span>{t('workspaceChangedFiles')}</span><strong>{status?.changed_count ?? 0}</strong></div>
            <div><span>{t('workspaceHead')}</span><strong className="mono">{status?.head_commit?.slice(0, 10) ?? '—'}</strong></div>
          </div>
          {data.error && <p className="form-error">{data.error}</p>}
          {status?.on_protected_branch && <p className="form-note">{t('workspaceProtectedBranch')}</p>}
          {status?.changed_files.length ? (
            <ul className="workspace-files">
              {status.changed_files.slice(0, 12).map((file) => <li key={file} className="mono">{file}</li>)}
            </ul>
          ) : (
            <p className="form-note">{t('workspaceNoFiles')}</p>
          )}
          <form
            className="workspace-branch-form"
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault()
              const input = new FormData(event.currentTarget).get('branch')
              const name = String(input ?? '').trim()
              if (name) newBranch.mutate(name)
            }}
          >
            <label className="field">
              <span>{t('workspaceNewBranch')}</span>
              <input name="branch" placeholder="aatm/task-1" maxLength={121} required />
            </label>
            <button className="button button-secondary" type="submit" disabled={newBranch.isPending}>
              {newBranch.isPending ? t('creating') : t('workspaceCreateBranch')}
            </button>
          </form>
          {newBranch.isSuccess && <p className="form-success"><Check size={13} />{t('workspaceBranchCreated')}</p>}
          {newBranch.isError && <p className="form-error">{t('requestFailed')}: {newBranch.error.message}</p>}
          <div className="form-actions">
            <button
              className="button button-secondary task-action-button"
              type="button"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              <Trash2 size={12} />{t('workspaceRemove')}
            </button>
          </div>
          {remove.isSuccess && <p className="form-success"><Check size={13} />{t('workspaceRemoved')}</p>}
          {remove.isError && <p className="form-error">{t('requestFailed')}: {remove.error.message}</p>}
        </>
      ) : (
        <>
          {!creating ? (
            <div className="form-actions">
              <button className="button button-primary" type="button" onClick={() => setCreating(true)}>
                <Plus size={14} />{t('workspaceCreate')}
              </button>
            </div>
          ) : (
            <form className="workspace-create-form" onSubmit={(event) => { event.preventDefault(); create.mutate() }}>
              <label className="field">
                <span>{t('workspaceSource')}</span>
                <input value={source} maxLength={1000} placeholder="/path/to/local/repo" onChange={(event) => setSource(event.target.value)} />
              </label>
              <p className="form-note">{t('workspaceSourceHint')}</p>
              <label className="field">
                <span>{t('workspaceNewBranch')}</span>
                <input value={branch} maxLength={121} placeholder="aatm/task-1" onChange={(event) => setBranch(event.target.value)} />
              </label>
              {create.isError && <p className="form-error">{t('requestFailed')}: {create.error.message}</p>}
              <div className="form-actions">
                <button className="button button-secondary" type="button" onClick={() => setCreating(false)}>{t('cancel')}</button>
                <button className="button button-primary" type="submit" disabled={create.isPending}>
                  {create.isPending ? t('workspaceCreating') : t('workspaceCreate')}
                </button>
              </div>
            </form>
          )}
          {create.isSuccess && <p className="form-success"><Check size={13} />{t('workspaceCreated')}</p>}
          {!create.isSuccess && !creating && <p className="form-note"><CircleAlert size={12} /> {t('workspaceNone')}</p>}
          {workspace.isFetching && <p className="form-note"><LoaderCircle className="spin" size={12} /> {t('loading')}</p>}
        </>
      )}
    </section>
  )
}
