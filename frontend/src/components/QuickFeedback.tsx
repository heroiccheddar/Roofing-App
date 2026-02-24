import { useState } from 'react'
import { submitFeedback } from '../api/client'
import { useOfflineQueue } from '../hooks/useOfflineQueue'

interface QuickFeedbackProps {
  zoneId: string
  zoneName?: string
  onClose: () => void
  onSubmitted?: () => void
}

/**
 * Compact feedback popup designed to fit in a Mapbox popup (~250px wide).
 *
 * Supports offline submission via the offline queue from Agent C.
 * Handles 409 (already rated) gracefully.
 */
function QuickFeedback({ zoneId, zoneName, onClose, onSubmitted }: QuickFeedbackProps) {
  const [rating, setRating] = useState(0)
  const [hoveredStar, setHoveredStar] = useState(0)
  const [visibleDamage, setVisibleDamage] = useState<boolean | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { isOnline, enqueue } = useOfflineQueue()

  const canSubmit = rating > 0 && !submitting && !submitted

  async function handleSubmit() {
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)

    const payload = {
      rating,
      visible_damage: visibleDamage ?? undefined,
    }

    if (!isOnline) {
      // Queue for later sync
      enqueue('feedback', zoneId, payload)
      setSubmitted(true)
      setSubmitting(false)
      setTimeout(() => {
        onSubmitted?.()
        onClose()
      }, 1500)
      return
    }

    try {
      await submitFeedback(zoneId, payload)
      setSubmitted(true)
      setSubmitting(false)
      setTimeout(() => {
        onSubmitted?.()
        onClose()
      }, 1500)
    } catch (err: unknown) {
      setSubmitting(false)
      const message = err instanceof Error ? err.message : String(err)
      if (message.includes('409') || message.toLowerCase().includes('already')) {
        // Already rated — treat as success
        setSubmitted(true)
        setTimeout(() => {
          onSubmitted?.()
          onClose()
        }, 1500)
      } else {
        setError(message)
      }
    }
  }

  if (submitted) {
    return (
      <div
        style={{
          width: 250,
          padding: '12px 14px',
          background: 'var(--success-bg)',
          color: 'var(--success-text)',
          borderRadius: 8,
          fontSize: 13,
          fontWeight: 600,
          textAlign: 'center',
        }}
      >
        {isOnline ? 'Feedback saved!' : 'Queued for sync when online'}
      </div>
    )
  }

  return (
    <div style={{ width: 250, padding: '12px 14px', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
          {zoneName ? `Rate: ${zoneName}` : 'Rate this zone'}
        </span>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            fontSize: 16,
            cursor: 'pointer',
            color: 'var(--text-tertiary)',
            padding: '0 4px',
            lineHeight: 1,
          }}
          aria-label="Close"
        >
          &times;
        </button>
      </div>

      {/* Offline indicator */}
      {!isOnline && (
        <div
          style={{
            fontSize: 11,
            color: '#92400e',
            background: '#fef3c7',
            padding: '4px 8px',
            borderRadius: 4,
            marginBottom: 8,
          }}
        >
          Offline — will sync when reconnected
        </div>
      )}

      {/* Star rating */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6, textTransform: 'uppercase' }}>
          Rating
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {[1, 2, 3, 4, 5].map((star) => (
            <button
              key={star}
              onClick={() => setRating(star)}
              onMouseEnter={() => setHoveredStar(star)}
              onMouseLeave={() => setHoveredStar(0)}
              style={{
                width: 32,
                height: 32,
                borderRadius: 4,
                border: 'none',
                background: 'none',
                fontSize: 22,
                cursor: 'pointer',
                padding: 0,
                color: star <= (hoveredStar || rating) ? '#f59e0b' : 'var(--border-primary)',
                transition: 'color 0.1s',
              }}
              aria-label={`${star} star${star !== 1 ? 's' : ''}`}
            >
              &#9733;
            </button>
          ))}
        </div>
      </div>

      {/* Damage toggle */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6, textTransform: 'uppercase' }}>
          Visible damage?
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {([true, false] as const).map((val) => (
            <button
              key={String(val)}
              onClick={() => setVisibleDamage(visibleDamage === val ? null : val)}
              style={{
                flex: 1,
                padding: '6px 0',
                borderRadius: 6,
                border: '1px solid var(--border-primary)',
                background: visibleDamage === val
                  ? (val ? 'var(--accent-red)' : 'var(--accent-green)')
                  : 'var(--bg-secondary)',
                color: visibleDamage === val ? '#fff' : 'var(--text-secondary)',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                minHeight: 36,
              }}
            >
              {val ? 'Yes' : 'No'}
            </button>
          ))}
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div
          style={{
            fontSize: 12,
            color: 'var(--error-text)',
            background: 'var(--error-bg)',
            padding: '6px 8px',
            borderRadius: 4,
            marginBottom: 8,
          }}
        >
          {error}
        </div>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!canSubmit}
        style={{
          width: '100%',
          padding: '8px 0',
          borderRadius: 6,
          border: 'none',
          background: canSubmit ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
          color: canSubmit ? '#fff' : 'var(--text-tertiary)',
          fontSize: 13,
          fontWeight: 600,
          cursor: canSubmit ? 'pointer' : 'not-allowed',
          minHeight: 36,
        }}
      >
        {submitting ? 'Submitting...' : 'Submit Feedback'}
      </button>
    </div>
  )
}

export default QuickFeedback
