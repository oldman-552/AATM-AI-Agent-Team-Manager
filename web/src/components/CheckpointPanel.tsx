import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { History, Plus, RotateCcw } from 'lucide-react'

import { api, Task } from '../api'
import { formatDateTime } from '../format'

/**
 * Durable checkpoints for a task.
 *
 * The panel never claims work resumed by itself: it shows the recorded resume
 * points and a plain-language plan the operator can act on.
 */
export function CheckpointPanel({ task }: { task: Task }) {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState('')
  const [note, setNote] = useState('')

  const checkpoints = useQuery({
    queryKey: ['checkpoints', task.id],
    queryFn: () => api.checkpoints(task.id),
    enabled: open,
  })
  const plan = useQuery({
    queryKey: ['resumePlan', task.id],
    queryFn: () => api.resumePlan(task.id),
    enabled: open,
  })
  const create = useMutation({
    mutationFn: () => api.createCheckpoint(task.id, { label, note }),
    onSuccess: async () => {
      setLabel('')
      setNote('')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['checkpoints', task.id] }),
        queryClient.invalidateQueries({ queryKey: ['resumePlan', task.id] }),
        queryClient.invalidateQueries({ queryKey: ['events'] }),
      ])
    },
  })

  return (
    <div className="checkpoint-panel">
      <button className="button button-secondary task-action-button" type="button" onClick={() => setOpen((value) => !value)}>
        <History size={12} /> {t('checkpointsToggle')}
      </button>
      {open && (
        <div className="checkpoint-body">
          {plan.data && (
            <ul className="checkpoint-plan">
              {plan.data.next_actions.map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ul>
          )}
          <div className="checkpoint-form">
            <label>
              <span>{t('checkpointLabel')}</span>
              <input value={label} maxLength={120} onChange={(event) => setLabel(event.target.value)} />
            </label>
            <label>
              <span>{t('checkpointNote')}</span>
              <input value={note} maxLength={500} onChange={(event) => setNote(event.target.value)} />
            </label>
            <button
              className="button button-primary task-action-button"
              type="button"
              disabled={create.isPending || !label.trim()}
              onClick={() => create.mutate()}
            >
              <Plus size={12} /> {t('checkpointAdd')}
            </button>
          </div>
          {create.isError && <p className="form-error">{t('requestFailed')}: {create.error.message}</p>}
          {checkpoints.data?.checkpoints.length ? (
            <ol className="checkpoint-list">
              {checkpoints.data.checkpoints.map((item) => (
                <li key={item.id}>
                  <span className="checkpoint-seq">#{item.sequence}</span>
                  <span>{item.label}</span>
                  <time>{formatDateTime(item.created_at, i18n.language)}</time>
                </li>
              ))}
            </ol>
          ) : (
            <p className="form-note">{t('checkpointEmpty')}</p>
          )}
          {plan.data?.resumed_automatically === false && <p className="form-note">{t('checkpointManualNote')}</p>}
          <p className="form-note"><RotateCcw size={11} /> {t('checkpointSecretNote')}</p>
        </div>
      )}
    </div>
  )
}
