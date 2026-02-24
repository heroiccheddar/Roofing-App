import { useState, useCallback } from 'react'
import useAppStore from '../stores/appStore'
import {
  startCanvassSession,
  updateCanvassSession,
  getZoneCanvassHistory,
} from '../api/client'
import type { CanvassSessionResponse } from '../types/api'

interface CanvassTrackerProps {
  zoneId: string
}

type TrackerState = 'idle' | 'active' | 'summary'

function CanvassTracker({ zoneId }: CanvassTrackerProps) {
  const activeCanvassSessionId = useAppStore((s) => s.activeCanvassSessionId)
  const setActiveCanvassSessionId = useAppStore((s) => s.setActiveCanvassSessionId)

  const [state, setState] = useState<TrackerState>(activeCanvassSessionId ? 'active' : 'idle')
  const [session, setSession] = useState<CanvassSessionResponse | null>(null)
  const [history, setHistory] = useState<CanvassSessionResponse[]>([])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Local counter state for optimistic UI
  const [counters, setCounters] = useState({
    doors_knocked: 0,
    doors_answered: 0,
    homeowner_interested: 0,
    inspections_scheduled: 0,
    contracts_signed: 0,
    visible_damage_count: 0,
  })
  const [rating, setRating] = useState(0)
  const [notes, setNotes] = useState('')
  const [showMore, setShowMore] = useState(false)

  const loadHistory = useCallback(async () => {
    try {
      const res = await getZoneCanvassHistory(zoneId)
      setHistory(res.sessions)
      setHistoryLoaded(true)
    } catch {
      // Silent — history is non-critical
    }
  }, [zoneId])

  // Load history on first render of idle state
  if (!historyLoaded && state === 'idle') {
    loadHistory()
  }

  const handleStart = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await startCanvassSession(zoneId)
      setSession(res)
      setActiveCanvassSessionId(res.id)
      setCounters({
        doors_knocked: 0,
        doors_answered: 0,
        homeowner_interested: 0,
        inspections_scheduled: 0,
        contracts_signed: 0,
        visible_damage_count: 0,
      })
      setRating(0)
      setNotes('')
      setState('active')
    } catch (err: any) {
      setError(err.message || 'Failed to start session')
    } finally {
      setLoading(false)
    }
  }

  const updateCounter = (field: keyof typeof counters, delta: number) => {
    setCounters((prev) => {
      const newVal = Math.max(0, prev[field] + delta)
      const updated = { ...prev, [field]: newVal }

      // Fire-and-forget PUT
      if (activeCanvassSessionId) {
        updateCanvassSession(activeCanvassSessionId, { [field]: newVal }).catch(() => {})
      }

      return updated
    })
  }

  const handleEndSession = async () => {
    if (!activeCanvassSessionId) return
    setLoading(true)
    setError(null)
    try {
      const res = await updateCanvassSession(activeCanvassSessionId, {
        ...counters,
        rating: rating > 0 ? rating : undefined,
        notes: notes.trim() || undefined,
      })
      setSession(res)
      setActiveCanvassSessionId(null)
      setState('summary')
    } catch (err: any) {
      setError(err.message || 'Failed to end session')
    } finally {
      setLoading(false)
    }
  }

  const handleDone = () => {
    setState('idle')
    setSession(null)
    setHistoryLoaded(false)
  }

  // ===== IDLE STATE =====
  if (state === 'idle') {
    return (
      <div style={styles.container}>
        <h3 style={styles.sectionTitle}>Canvass Tracker</h3>
        <button onClick={handleStart} disabled={loading} style={styles.primaryBtn}>
          {loading ? 'Starting...' : 'Start Canvassing'}
        </button>
        {error && <div style={styles.error}>{error}</div>}
        {history.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 6 }}>
              Previous sessions ({history.length})
            </div>
            {history.slice(0, 3).map((s) => (
              <div key={s.id} style={styles.historyCard}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, color: '#475569' }}>
                    {new Date(s.created_at).toLocaleDateString()}
                  </span>
                  {s.rating != null && (
                    <span style={{ fontSize: 12, color: '#eab308' }}>
                      {'★'.repeat(s.rating)}{'☆'.repeat(5 - s.rating)}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 13, color: '#0f172a', marginTop: 2 }}>
                  {s.doors_knocked ?? 0} knocked · {s.doors_answered ?? 0} answered · {s.homeowner_interested ?? 0} interested
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // ===== ACTIVE STATE =====
  if (state === 'active') {
    return (
      <div style={styles.container}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ ...styles.sectionTitle, margin: 0 }}>Canvassing</h3>
          <span style={styles.liveBadge}>LIVE</span>
        </div>

        <CounterRow label="Doors Knocked" value={counters.doors_knocked} onIncrement={() => updateCounter('doors_knocked', 1)} onDecrement={() => updateCounter('doors_knocked', -1)} />
        <CounterRow label="Doors Answered" value={counters.doors_answered} onIncrement={() => updateCounter('doors_answered', 1)} onDecrement={() => updateCounter('doors_answered', -1)} />
        <CounterRow label="Interested" value={counters.homeowner_interested} onIncrement={() => updateCounter('homeowner_interested', 1)} onDecrement={() => updateCounter('homeowner_interested', -1)} />
        <CounterRow label="Visible Damage" value={counters.visible_damage_count} onIncrement={() => updateCounter('visible_damage_count', 1)} onDecrement={() => updateCounter('visible_damage_count', -1)} />

        <button
          onClick={() => setShowMore(!showMore)}
          style={{ ...styles.linkBtn, marginTop: 8 }}
        >
          {showMore ? 'Hide Details' : 'More Details'}
        </button>

        {showMore && (
          <div style={{ marginTop: 8 }}>
            <CounterRow label="Inspections" value={counters.inspections_scheduled} onIncrement={() => updateCounter('inspections_scheduled', 1)} onDecrement={() => updateCounter('inspections_scheduled', -1)} />
            <CounterRow label="Contracts" value={counters.contracts_signed} onIncrement={() => updateCounter('contracts_signed', 1)} onDecrement={() => updateCounter('contracts_signed', -1)} />
          </div>
        )}

        {/* Star Rating */}
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>Zone Rating</div>
          <div style={{ display: 'flex', gap: 4, fontSize: 24 }}>
            {[1, 2, 3, 4, 5].map((star) => (
              <span
                key={star}
                onClick={() => setRating(star === rating ? 0 : star)}
                style={{ cursor: 'pointer', color: star <= rating ? '#eab308' : '#cbd5e1', userSelect: 'none' }}
              >
                {star <= rating ? '\u2605' : '\u2606'}
              </span>
            ))}
          </div>
        </div>

        {/* Notes */}
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value.slice(0, 1000))}
          placeholder="Notes..."
          style={styles.textarea}
        />

        {error && <div style={styles.error}>{error}</div>}

        <button onClick={handleEndSession} disabled={loading} style={styles.endBtn}>
          {loading ? 'Saving...' : 'End Session'}
        </button>
      </div>
    )
  }

  // ===== SUMMARY STATE =====
  return (
    <div style={styles.container}>
      <h3 style={styles.sectionTitle}>Session Complete</h3>
      {session && (
        <div style={styles.summaryGrid}>
          <SummaryStat label="Doors Knocked" value={session.doors_knocked ?? 0} />
          <SummaryStat label="Answered" value={session.doors_answered ?? 0} />
          <SummaryStat label="Interested" value={session.homeowner_interested ?? 0} />
          <SummaryStat label="Damage Spotted" value={session.visible_damage_count ?? 0} />
          <SummaryStat label="Inspections" value={session.inspections_scheduled ?? 0} />
          <SummaryStat label="Contracts" value={session.contracts_signed ?? 0} />
          {(session.doors_knocked ?? 0) > 0 && (
            <SummaryStat
              label="Answer Rate"
              value={`${(((session.doors_answered ?? 0) / (session.doors_knocked ?? 1)) * 100).toFixed(0)}%`}
            />
          )}
          {session.rating != null && (
            <div style={styles.summaryItem}>
              <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase' }}>Rating</div>
              <div style={{ fontSize: 16, color: '#eab308' }}>
                {'★'.repeat(session.rating)}{'☆'.repeat(5 - session.rating)}
              </div>
            </div>
          )}
        </div>
      )}
      <button onClick={handleDone} style={styles.primaryBtn}>
        Done
      </button>
    </div>
  )
}

// ===== Sub-components =====

function CounterRow({
  label,
  value,
  onIncrement,
  onDecrement,
}: {
  label: string
  value: number
  onIncrement: () => void
  onDecrement: () => void
}) {
  return (
    <div style={styles.counterRow}>
      <span style={styles.counterLabel}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button onClick={onDecrement} style={styles.counterBtn} disabled={value === 0}>
          -
        </button>
        <span style={styles.counterValue}>{value}</span>
        <button onClick={onIncrement} style={styles.counterBtn}>
          +
        </button>
      </div>
    </div>
  )
}

function SummaryStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div style={styles.summaryItem}>
      <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#0f172a' }}>{value}</div>
    </div>
  )
}

// ===== Styles =====

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: 16,
    backgroundColor: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: 8,
  },
  sectionTitle: {
    margin: '0 0 12px',
    fontSize: 14,
    fontWeight: 600,
    color: '#0f172a',
  },
  primaryBtn: {
    width: '100%',
    padding: 12,
    fontSize: 14,
    fontWeight: 600,
    color: '#fff',
    backgroundColor: '#2563eb',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
  },
  endBtn: {
    width: '100%',
    padding: 12,
    marginTop: 12,
    fontSize: 14,
    fontWeight: 600,
    color: '#fff',
    backgroundColor: '#dc2626',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
  },
  linkBtn: {
    background: 'none',
    border: 'none',
    color: '#2563eb',
    fontSize: 13,
    cursor: 'pointer',
    padding: 0,
  },
  liveBadge: {
    fontSize: 11,
    fontWeight: 700,
    color: '#dc2626',
    padding: '2px 8px',
    borderRadius: 4,
    backgroundColor: '#fef2f2',
    letterSpacing: 1,
  },
  counterRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 0',
    borderBottom: '1px solid #e2e8f0',
  },
  counterLabel: {
    fontSize: 14,
    color: '#334155',
    fontWeight: 500,
  },
  counterBtn: {
    width: 44,
    height: 44,
    fontSize: 20,
    fontWeight: 700,
    borderRadius: 8,
    border: '1px solid #e2e8f0',
    backgroundColor: '#fff',
    color: '#0f172a',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  counterValue: {
    fontSize: 20,
    fontWeight: 700,
    color: '#0f172a',
    minWidth: 32,
    textAlign: 'center' as const,
  },
  textarea: {
    width: '100%',
    minHeight: 60,
    marginTop: 8,
    padding: 8,
    fontSize: 13,
    border: '1px solid #e2e8f0',
    borderRadius: 6,
    resize: 'vertical' as const,
    fontFamily: 'inherit',
  },
  error: {
    marginTop: 8,
    padding: 8,
    backgroundColor: '#fef2f2',
    border: '1px solid #fecaca',
    borderRadius: 6,
    color: '#991b1b',
    fontSize: 13,
  },
  historyCard: {
    padding: 8,
    marginBottom: 4,
    backgroundColor: '#fff',
    borderRadius: 6,
    border: '1px solid #e2e8f0',
  },
  summaryGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 8,
    backgroundColor: '#fff',
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
  },
  summaryItem: {
    padding: 4,
  },
}

export default CanvassTracker
