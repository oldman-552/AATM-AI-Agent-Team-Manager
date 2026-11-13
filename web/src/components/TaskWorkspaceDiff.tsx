import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { FileDiff, LoaderCircle } from 'lucide-react'

import { api } from '../api'

export default function TaskWorkspaceDiff({ projectId, taskId }: { projectId: string; taskId: string }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const query = useQuery({
    queryKey: ['taskWorkspaceDiff', projectId, taskId],
    queryFn: () => api.taskWorkspaceDiff(projectId, taskId),
    enabled: open,
  })
  const preview = query.data?.preview

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
                    {t('taskDiffReadOnly')}{' '}{t('taskDiffUntracked')}
                    {preview.truncated ? ` ${t('taskDiffTruncated')}` : ''}
                  </p>
                  {preview.diff ? (
                    <pre className="task-diff-preview" dir="ltr"><code>{preview.diff}</code></pre>
                  ) : <p className="form-note">{t('taskDiffEmpty')}</p>}
                </>
              )
      )}
    </div>
  )
}
