import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Bell, CheckCheck } from 'lucide-react'

import { api, NotificationItem } from '../api'
import { formatDateTime, formatNumber } from '../format'

/**
 * Notifications come from real pending work on the server (pending approvals,
 * failed/rework tasks, expired leases). The browser only stores nothing: read
 * state is persisted by the API, so it survives a restart.
 */
export function NotificationCenter({ onNavigate }: { onNavigate: (view: string) => void }) {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  const notifications = useQuery({
    queryKey: ['notifications'],
    queryFn: api.notifications,
    refetchInterval: 30_000,
  })
  const markAll = useMutation({
    mutationFn: api.markAllNotificationsRead,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
  const markOne = useMutation({
    mutationFn: (id: string) => api.markNotificationsRead([id]),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (open && containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  const unread = notifications.data?.unread ?? 0
  const items = notifications.data?.notifications ?? []
  const language = i18n.language

  function message(item: NotificationItem): string {
    const data = item.data as Record<string, string | number>
    const base = t(item.message_key, { ...data })
    return base === item.message_key ? item.message_key : base
  }

  function openItem(item: NotificationItem) {
    if (!item.read) markOne.mutate(item.id)
    setOpen(false)
    onNavigate(item.action_view)
  }

  return (
    <div className="notification-center" ref={containerRef}>
      <button
        className="icon-button notification-trigger"
        type="button"
        aria-label={t('notificationsTitle')}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Bell size={17} />
        {unread > 0 && <span className="notification-badge">{formatNumber(unread, language)}</span>}
      </button>
      {open && (
        <div className="notification-panel" role="dialog" aria-label={t('notificationsTitle')}>
          <div className="notification-header">
            <strong>{t('notificationsTitle')}</strong>
            {unread > 0 && (
              <button className="button button-secondary" type="button" disabled={markAll.isPending} onClick={() => markAll.mutate()}>
                <CheckCheck size={12} /> {t('notificationsMarkAll')}
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="form-note">{t('notificationsEmpty')}</p>
          ) : (
            <ul className="notification-list">
              {items.map((item) => (
                <li key={item.id} className={`notification-item ${item.read ? 'read' : ''} ${item.severity}`}>
                  <button type="button" onClick={() => openItem(item)}>
                    <span className="notification-dot" aria-hidden="true" />
                    <span className="notification-text">{message(item)}</span>
                    {item.created_at && <time>{formatDateTime(/(?:Z|[+-]\d{2}:\d{2})$/.test(item.created_at) ? item.created_at : `${item.created_at}Z`, language)}</time>}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="form-note">{t('notificationsSource')}</p>
        </div>
      )}
    </div>
  )
}
