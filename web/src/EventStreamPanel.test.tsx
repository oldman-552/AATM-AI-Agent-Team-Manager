/**
 * @vitest-environment jsdom
 *
 * The stream panel's important behaviour is not "it connects" but "a reconnect
 * resumes from the last event instead of replaying or skipping".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, waitFor } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'

import i18n from './i18n'
import EventStreamPanel from './EventStreamPanel'

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

const auditEvent = (id: string, summary: string) => ({
  id, entity_type: 'project', entity_id: 'p1', event_type: 'project.created',
  summary, created_at: '2026-11-13T10:00:00Z',
})

beforeEach(async () => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  await i18n.changeLanguage('en')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function mount() {
  return render(
    <I18nextProvider i18n={i18n}>
      <EventStreamPanel />
    </I18nextProvider>,
  )
}

describe('live event stream panel', () => {
  it('connects without a cursor on first mount and renders incoming events', async () => {
    const { container } = mount()
    const source = FakeEventSource.instances[0]
    expect(source.url).toBe('/api/v1/events/stream')

    source.emit('hello', { delivery: 'poll' })
    source.emit('audit', auditEvent('e1', 'project created'))
    await waitFor(() => expect(container.textContent).toContain('project created'))
  })

  it('resumes from the last seen id after the server closes the stream', async () => {
    mount()
    const first = FakeEventSource.instances[0]
    first.emit('hello', { delivery: 'poll' })
    first.emit('audit', auditEvent('event-42', 'first event'))

    // The server ends the stream on purpose; the client must re-subscribe with
    // its cursor, not start over from live.
    first.emit('close', { reason: 'max_seconds_reached' })
    await waitFor(() => expect(FakeEventSource.instances.length).toBeGreaterThan(1))
    expect(FakeEventSource.instances[1].url).toContain('last_event_id=event-42')
  })

  it('keeps events across a reconnect instead of dropping them', async () => {
    const { container } = mount()
    FakeEventSource.instances[0].emit('audit', auditEvent('e1', 'survives reconnect'))
    FakeEventSource.instances[0].emit('close', { reason: 'max_seconds_reached' })
    await waitFor(() => expect(FakeEventSource.instances.length).toBeGreaterThan(1))
    expect(container.textContent).toContain('survives reconnect')
  })

  it('does not crash on a malformed frame', async () => {
    const { container } = mount()
    const source = FakeEventSource.instances[0]
    // Emit invalid JSON directly: a bad frame must not tear down the stream.
    for (const handler of (source as unknown as { listeners: Map<string, ((e: MessageEvent) => void)[]> })
      .listeners.get('audit') ?? []) {
      handler({ data: '{not json' } as MessageEvent)
    }
    source.emit('audit', auditEvent('e9', 'still working'))
    await waitFor(() => expect(container.textContent).toContain('still working'))
  })
})
