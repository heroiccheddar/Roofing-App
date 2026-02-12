import { useState } from 'react'
import { submitFeedback } from '../api/client'

interface FeedbackFormProps {
  zoneId: string
  onSubmitted?: () => void
}

function FeedbackForm({ zoneId, onSubmitted }: FeedbackFormProps) {
  const [rating, setRating] = useState<number>(0)
  const [hoveredRating, setHoveredRating] = useState<number>(0)
  const [visibleDamage, setVisibleDamage] = useState<boolean | null>(null)
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (rating === 0) {
      setError('Please select a rating')
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      await submitFeedback(zoneId, {
        rating,
        visible_damage: visibleDamage ?? undefined,
        notes: notes.trim() || undefined,
      })
      setSuccess(true)
      onSubmitted?.()
    } catch (err: any) {
      if (err.message?.includes('409') || err.message?.toLowerCase().includes('already')) {
        setError('You have already submitted feedback for this zone')
      } else {
        setError(err.message || 'Failed to submit feedback')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (success) {
    return (
      <div
        style={{
          padding: '1.5rem',
          backgroundColor: '#f0fdf4',
          border: '1px solid #86efac',
          borderRadius: '8px',
          color: '#166534',
        }}
      >
        <div style={{ fontSize: '1.125rem', fontWeight: '600', marginBottom: '0.5rem' }}>
          Feedback submitted!
        </div>
        <div style={{ color: '#15803d' }}>Thank you for your feedback.</div>
      </div>
    )
  }

  return (
    <div
      style={{
        padding: '1.5rem',
        backgroundColor: '#f8fafc',
        border: '1px solid #e2e8f0',
        borderRadius: '8px',
      }}
    >
      <h3 style={{ margin: '0 0 1.5rem 0', fontSize: '1.125rem', fontWeight: '600', color: '#0f172a' }}>
        Submit Zone Feedback
      </h3>

      {/* Star Rating */}
      <div style={{ marginBottom: '1.5rem' }}>
        <label
          style={{
            display: 'block',
            marginBottom: '0.5rem',
            fontSize: '0.875rem',
            fontWeight: '500',
            color: '#0f172a',
          }}
        >
          Zone Quality Rating
        </label>
        <div style={{ display: 'flex', gap: '0.25rem', fontSize: '2rem' }}>
          {[1, 2, 3, 4, 5].map((star) => (
            <span
              key={star}
              onClick={() => setRating(star)}
              onMouseEnter={() => setHoveredRating(star)}
              onMouseLeave={() => setHoveredRating(0)}
              style={{
                cursor: 'pointer',
                color: star <= (hoveredRating || rating) ? '#eab308' : '#cbd5e1',
                transition: 'color 0.15s',
                userSelect: 'none',
              }}
            >
              {star <= (hoveredRating || rating) ? '★' : '☆'}
            </span>
          ))}
        </div>
        {rating > 0 && (
          <div style={{ marginTop: '0.25rem', fontSize: '0.75rem', color: '#64748b' }}>
            {rating === 1 && 'Poor - Not worth pursuing'}
            {rating === 2 && 'Below Average - Limited potential'}
            {rating === 3 && 'Average - Moderate potential'}
            {rating === 4 && 'Good - Strong potential'}
            {rating === 5 && 'Excellent - High-quality leads'}
          </div>
        )}
      </div>

      {/* Visible Damage Toggle */}
      <div style={{ marginBottom: '1.5rem' }}>
        <label
          style={{
            display: 'block',
            marginBottom: '0.5rem',
            fontSize: '0.875rem',
            fontWeight: '500',
            color: '#0f172a',
          }}
        >
          Visible roof damage observed?
        </label>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            type="button"
            onClick={() => setVisibleDamage(true)}
            style={{
              padding: '0.5rem 1rem',
              fontSize: '0.875rem',
              fontWeight: '500',
              color: visibleDamage === true ? '#ffffff' : '#0f172a',
              backgroundColor: visibleDamage === true ? '#2563eb' : '#ffffff',
              border: `1px solid ${visibleDamage === true ? '#2563eb' : '#cbd5e1'}`,
              borderRadius: '6px',
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
          >
            Yes
          </button>
          <button
            type="button"
            onClick={() => setVisibleDamage(false)}
            style={{
              padding: '0.5rem 1rem',
              fontSize: '0.875rem',
              fontWeight: '500',
              color: visibleDamage === false ? '#ffffff' : '#0f172a',
              backgroundColor: visibleDamage === false ? '#2563eb' : '#ffffff',
              border: `1px solid ${visibleDamage === false ? '#2563eb' : '#cbd5e1'}`,
              borderRadius: '6px',
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
          >
            No
          </button>
          {visibleDamage !== null && (
            <button
              type="button"
              onClick={() => setVisibleDamage(null)}
              style={{
                padding: '0.5rem 1rem',
                fontSize: '0.875rem',
                color: '#64748b',
                backgroundColor: 'transparent',
                border: 'none',
                cursor: 'pointer',
                textDecoration: 'underline',
              }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Notes Textarea */}
      <div style={{ marginBottom: '1.5rem' }}>
        <label
          style={{
            display: 'block',
            marginBottom: '0.5rem',
            fontSize: '0.875rem',
            fontWeight: '500',
            color: '#0f172a',
          }}
        >
          Notes (optional)
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value.slice(0, 1000))}
          placeholder="Additional observations about this zone..."
          style={{
            width: '100%',
            minHeight: '80px',
            padding: '0.5rem',
            fontSize: '0.875rem',
            color: '#0f172a',
            backgroundColor: '#ffffff',
            border: '1px solid #cbd5e1',
            borderRadius: '6px',
            resize: 'vertical',
            fontFamily: 'inherit',
          }}
        />
        <div style={{ marginTop: '0.25rem', fontSize: '0.75rem', color: '#94a3b8', textAlign: 'right' }}>
          {notes.length}/1000
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div
          style={{
            marginBottom: '1rem',
            padding: '0.75rem',
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '6px',
            color: '#991b1b',
            fontSize: '0.875rem',
          }}
        >
          {error}
        </div>
      )}

      {/* Submit Button */}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={submitting || rating === 0}
        style={{
          width: '100%',
          padding: '0.75rem',
          fontSize: '0.875rem',
          fontWeight: '600',
          color: '#ffffff',
          backgroundColor: submitting || rating === 0 ? '#94a3b8' : '#2563eb',
          border: 'none',
          borderRadius: '6px',
          cursor: submitting || rating === 0 ? 'not-allowed' : 'pointer',
          transition: 'background-color 0.15s',
        }}
      >
        {submitting ? 'Submitting...' : 'Submit Feedback'}
      </button>
    </div>
  )
}

export default FeedbackForm
