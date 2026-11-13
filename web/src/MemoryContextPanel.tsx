import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { CircleAlert, Layers, LoaderCircle, Scissors, Sparkles } from 'lucide-react'

import { api } from './api'
import { formatNumber } from './format'

/**
 * Context selection is shown with its omissions. An excluded entry is listed
 * with the reason, because a silently dropped requirement is the expensive
 * failure mode; and a summarised entry states that its text is verbatim.
 */
export default function MemoryContextPanel({ projectId }: { projectId: string }) {
  const { t, i18n } = useTranslation()
  const [query, setQuery] = useState('')
  const [budget, setBudget] = useState(400)
  const [submitted, setSubmitted] = useState<{ q: string; budget: number } | null>(null)

  const context = useQuery({
    queryKey: ['memoryContext', projectId, submitted],
    queryFn: () => api.memoryContext({ projectId: projectId || undefined, q: submitted?.q, wordBudget: submitted?.budget }),
    enabled: submitted !== null,
  })

  return (
    <section className="panel memory-context-panel">
      <div className="panel-heading">
        <div><span className="panel-kicker">{t('memoryContextKicker')}</span><h3>{t('memoryContextTitle')}</h3></div>
        <span className="panel-icon"><Layers size={17} /></span>
      </div>
      <p className="panel-note">{t('memoryContextNote')}</p>
      <div className="memory-context-controls">
        <label className="field">
          <span>{t('memoryContextQuery')}</span>
          <input value={query} maxLength={500} placeholder={t('memoryContextQueryPlaceholder')} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label className="field">
          <span>{t('memoryContextBudget')}</span>
          <input type="number" min={10} max={4000} value={budget} onChange={(event) => setBudget(Number(event.target.value))} />
        </label>
        <button className="button button-primary" type="button" onClick={() => setSubmitted({ q: query, budget })}>
          <Sparkles size={14} />{t('memoryContextSelect')}
        </button>
      </div>

      {submitted === null ? <p className="form-note">{t('memoryContextIdle')}</p>
        : context.isLoading ? <p className="form-note"><LoaderCircle className="spin" size={13} /> {t('loading')}</p>
        : context.isError || !context.data ? <p className="form-error">{t('loadError')}</p>
        : (
          <>
            <div className="memory-context-budget">
              <div className="memory-budget-bar">
                <span style={{ inlineSize: `${Math.min(100, (context.data.budget.words_used / context.data.budget.word_budget) * 100)}%` }} />
              </div>
              <p className="form-note">
                {formatNumber(context.data.budget.words_used, i18n.language)} / {formatNumber(context.data.budget.word_budget, i18n.language)} {context.data.budget.unit}
                {' · '}{context.data.budget.note}
              </p>
            </div>

            <ul className="memory-context-list">
              {context.data.selected.map((item) => (
                <li key={item.memory_id} className={`memory-context-item ${item.included_as}`}>
                  <div className="memory-context-head">
                    <strong>{item.title}</strong>
                    <span className="state-badge small">{item.scope}</span>
                    <span className="recovery-tag manual">{item.kind}</span>
                    {item.included_as === 'summary'
                      ? <span className="recovery-tag auto"><Scissors size={10} />{t('memoryContextSummarized')}</span>
                      : <span className="recovery-tag na">{t('memoryContextFull')}</span>}
                    <small>{formatNumber(item.words, i18n.language)} {t('memoryContextWords')}</small>
                  </div>
                  {item.summary && <p className="memory-context-summary">{item.summary}</p>}
                  {item.summary && <span className="builder-source">{t('memoryContextVerbatim')}</span>}
                </li>
              ))}
            </ul>

            {context.data.excluded.length > 0 && (
              <div className="memory-context-excluded">
                <h4><CircleAlert size={13} /> {t('memoryContextExcluded')} ({context.data.excluded.length})</h4>
                <ul>
                  {context.data.excluded.map((item) => (
                    <li key={item.memory_id}><span>{item.title}</span><small>{item.reason}</small></li>
                  ))}
                </ul>
              </div>
            )}

            <p className="form-note">{context.data.note} {context.data.ranking.note}</p>
          </>
        )}
    </section>
  )
}
