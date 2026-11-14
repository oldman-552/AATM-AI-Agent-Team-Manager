import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { FileDiff, GitMerge, LoaderCircle } from 'lucide-react'

import { api } from '../api'

const untrackedStatusTranslation: Record<string, string> = {
  binary: 'taskDiffBinary',
  symlink: 'taskDiffSymlink',
  unsafe: 'taskDiffUnsafe',
  non_regular: 'taskDiffNonRegular',
  unreadable: 'taskDiffUnreadable',
  too_large: 'taskDiffTooLarge',
  omitted_limit: 'taskDiffOmitted',
}

export default function TaskWorkspaceDiff({ projectId, taskId, taskState }: { projectId: string; taskId: string; taskState: string }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const query = useQuery({
    queryKey: ['taskWorkspaceDiff', projectId, taskId],
    queryFn: () => api.taskWorkspaceDiff(projectId, taskId),
    enabled: open,
  })
  const preview = query.data?.preview
  const reviews = useQuery({
    queryKey: ['taskReviews', taskId],
    queryFn: () => api.taskReviews(taskId),
    enabled: open && taskState === 'approved',
  })
  const integration = useMutation({
    mutationFn: () => api.integrateTaskWorkspace(projectId, taskId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['taskWorkspaceDiff', projectId, taskId] }),
        queryClient.invalidateQueries({ queryKey: ['taskWorkspace', projectId, taskId] }),
        queryClient.invalidateQueries({ queryKey: ['workspace', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
      ])
    },
  })
  const reviewedCurrentCommit = Boolean(
    preview && reviews.data?.reviews.some(
      (review) => review.verdict === 'approved' && review.task_worktree_head === preview.head_commit,
    ),
  )
  const canIntegrate = Boolean(
    taskState === 'approved' && reviewedCurrentCommit && preview &&
    preview.base_commit !== preview.head_commit && !preview.truncated &&
    !preview.untracked_truncated && preview.untracked_files.length === 0 && preview.diff,
  )

  return (
    <div className="task-diff-block">
      <button
        className="button button-quiet"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <FileDiff size={14} />{open ? t('taskDiffHide') : t('taskDiffShow')}
      </button>
      {open && (
        query.isLoading ? <p className="form-note"><LoaderCircle className="spin" size={13} /> {t('loading')}</p>
          : query.isError ? <p className="form-error">{t('taskDiffError')}: {query.error.message}</p>
            : !query.data?.available || !preview ? <p className="form-note">{t('taskDiffUnavailable')}</p>
              : (
                <>
                  <p className="form-note">
                    {t('taskDiffBase')}: <code>{preview.base_commit.slice(0, 12)}</code>
                    {' · '}{t('taskDiffHead')}: <code>{preview.head_commit.slice(0, 12)}</code>
                  </p>
                  <p className="form-note">
                    {t('taskDiffReadOnly')}{' '}
                    {t('taskDiffUntracked')} ({preview.untracked_files.length})
                    {preview.truncated ? ` ${t('taskDiffTruncated')}` : ''}
                  </p>
                  {preview.diff ? (
                    <pre className="task-diff-preview" dir="ltr"><code>{preview.diff}</code></pre>
                  ) : <p className="form-note">{t('taskDiffEmpty')}</p>}
                  {preview.untracked_files.length > 0 && (
                    <div className="task-untracked-list">
                      {preview.untracked_files.map((file) => (
                        <section className="task-untracked-file" key={file.path}>
                          <strong className="mono">{file.path}</strong>
                          {file.status === 'text' && file.content !== null ? (
                            <>
                              {file.truncated && <p className="form-note">{t('taskDiffFileTruncated')}</p>}
                              <pre className="task-diff-preview" dir="ltr"><code>{file.content}</code></pre>
                            </>
                          ) : <p className="form-note">{t(untrackedStatusTranslation[file.status] ?? 'taskDiffUnsafe')}</p>}
                        </section>
                      ))}
                      {preview.untracked_truncated && <p className="form-note">{t('taskDiffListTruncated')}</p>}
                    </div>
                  )}
                  {taskState === 'approved' && preview.base_commit !== preview.head_commit && !reviews.isLoading && !reviewedCurrentCommit && (
                    <p className="form-note">{t('taskDiffReviewRequired')}</p>
                  )}
                  {canIntegrate && !integration.isSuccess && (
                    <button
                      className="button button-secondary"
                      type="button"
                      disabled={integration.isPending}
                      onClick={() => {
                        if (window.confirm(t('taskDiffIntegrateConfirm'))) integration.mutate()
                      }}
                    >
                      <GitMerge size={14} />{integration.isPending ? t('taskDiffIntegrating') : t('taskDiffIntegrate')}
                    </button>
                  )}
                  {integration.isError && <p className="form-error">{t('taskDiffIntegrationError')}: {integration.error.message}</p>}
                  {integration.isSuccess && <p className="form-note">{t('taskDiffIntegrated', { branch: integration.data.branch })}</p>}
                </>
              )
      )}
    </div>
  )
}
