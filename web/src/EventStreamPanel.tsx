import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Radio } from 'lucide-react'

import { eventStreamUrl, type AuditEvent } from './api'

type StreamStatus = 'connecting' | 'live' | 'reconnecting' | 'closed'

/**
 * Live audit feed over server-sent events.
 *
 * Deliberate behaviours, each for a reason:
 * - Resumes with the last id seen, so a reconnect does not duplicate or skip.
 * - Backs off on failure instead of hammering a server that is down.
 * - The server closes the stream on purpose after a bounded time; that is a
 *   normal end, not an error, and the client reconnects with its cursor.
 * - Says "polled" in the UI, because the server polls the table rather than
 *   receiving pushes from a broker. Calling it real-time push would be a lie.
 */
export default function EventStreamPanel() {
  const { t } = useTranslation()
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [status, setStatus] = useState<StreamStatus>('connecting')
  const [attempts, setAttempts] = useState(0)
  const lastId = useRef<string | null>(null)
  const retryTimer = useRef<number | null>(null)

  useEffect(() => {
    let closed = false
    let source: EventSource | null = null
    let backoff = 1000

    const connect = () => {
      if (closed) return
      setStatus(attempts > 0 ? 'reconnecting' : 'connecting')
      source = new EventSource(eventStreamUrl(lastId.current))

      source.addEventListener('hello', () => {
        setStatus('live')
        backoff = 1000
      })

      source.addEventListener('audit', (message) => {
        try {
          const event = JSON.parse((message as MessageEvent).data) as AuditEvent
          if (event.id) lastId.current = event.id
          setEvents((current) => [event, ...current].slice(0, 50))
        } catch {
          // A malformed frame is not worth tearing the stream down over.
        }
      })

      source.addEventListener('close', () => {
        // The server ended the stream on purpose (bounded lifetime).
        setStatus('closed')
        source?.close()
        if (closed) return
        retryTimer.current = window.setTimeout(connect, 250)
      })

      source.addEventListener('error', () => {
        // EventSource auto-reconnects, but it ignores our cursor, so close it and
        // resume ourselves with exponential backoff.
        source?.close()
        if (closed) return
        setStatus('reconnecting')
        setAttempts((count) => count + 1)
        retryTimer.current = window.setTimeout(connect, backoff)
        backoff = Math.min(backoff * 2, 15_000)
      })
    }

    connect()

    return () => {
      closed = true
      source?.close()
      if (retryTimer.current !== null) window.clearTimeout(retryTimer.current)
    }
    // Mount once: the cursor lives in a ref, so re-running would restart the feed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const label =
    status === 'live' ? t('streamLive')
      : status === 'reconnecting' ? t('streamReconnecting')
        : status === 'closed' ? t('streamPaused')
          : t('loading')

  return (
    <>
      <div className="panel-heading">
        <div><span className="panel-kicker">{t('streamKicker')}</span><h3>{t('streamTitle')}</h3></div>
        <span className="panel-icon"><Radio size={17} className={status === 'live' ? 'pulse' : ''} /></span>
      </div>
      <p className="panel-note">
        <span className={`stream-dot ${status}`} /> {label} · {t('streamPolledNote')}
        {attempts > 0 && status !== 'live' ? ` · ${t('streamRetries', { count: attempts })}` : ''}
      </p>
      {events.length === 0
        ? <p className="form-note">{t('streamEmpty')}</p>
        : (
          <ul className="ops-event-list">
            {events.map((event) => (
              <li key={event.id}>
                <span className="ops-event-type">{event.event_type}</span>
                <span className="ops-event-summary">{event.summary}</span>
                <small>{new Date(event.created_at).toISOString().slice(11, 19)}</small>
              </li>
            ))}
          </ul>
        )}
    </>
  )
}
