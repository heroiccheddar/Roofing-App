/**
 * Shared UI helper components for zone detail display.
 *
 * Extracted from ZonePanel to share with ZoneDetail page.
 */
import { useState, useRef, useEffect } from 'react'

export function InfoTip({ text }: { text: string }) {
  const [show, setShow] = useState(false)
  const tipRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (show && tipRef.current) {
      const rect = tipRef.current.getBoundingClientRect()
      if (rect.right > window.innerWidth - 8) {
        tipRef.current.style.left = 'auto'
        tipRef.current.style.right = '0px'
      }
      if (rect.left < 8) {
        tipRef.current.style.left = '0px'
        tipRef.current.style.right = 'auto'
      }
    }
  }, [show])

  return (
    <span
      style={{ position: 'relative', display: 'inline-flex', marginLeft: 4, cursor: 'help' }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style={{ opacity: 0.45 }}>
        <circle cx="8" cy="8" r="7" stroke="#64748b" strokeWidth="1.5" />
        <text x="8" y="12" textAnchor="middle" fontSize="10" fontWeight="700" fill="#64748b">i</text>
      </svg>
      {show && (
        <div
          ref={tipRef}
          style={{
            position: 'absolute', bottom: 18, left: -8,
            background: '#1e293b', color: '#f1f5f9', fontSize: 11, lineHeight: '15px',
            padding: '6px 10px', borderRadius: 6, whiteSpace: 'normal',
            width: 200, maxWidth: 'calc(100vw - 32px)', zIndex: 100, boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            pointerEvents: 'none',
          }}
        >
          {text}
        </div>
      )}
    </span>
  )
}

export function Stat({ label, value, info }: { label: string; value: string; info?: string }) {
  return (
    <div style={{ padding: 8 }}>
      <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
        {label}
        {info && <InfoTip text={info} />}
      </div>
      <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>{value}</div>
    </div>
  )
}

export function ExposureBar({ score }: { score: number }) {
  const color = score > 60 ? '#dc2626' : score > 30 ? '#ca8a04' : '#16a34a'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
      <div style={{ flex: 1, height: 8, background: '#e2e8f0', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(score, 100)}%`, height: '100%', background: color, borderRadius: 4 }} />
      </div>
      <span style={{ fontSize: 14, fontWeight: 600, color, minWidth: 32 }}>{score.toFixed(0)}</span>
    </div>
  )
}

export function SubScoreBar({ label, value, color }: { label: string; value?: number; color: string }) {
  if (value == null) return null
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
        <span>{label}</span>
        <span style={{ fontWeight: 600 }}>{value.toFixed(0)}</span>
      </div>
      <div style={{ height: 6, background: '#e0e0e0', borderRadius: 3 }}>
        <div style={{ height: '100%', width: `${Math.min(value, 100)}%`, background: color, borderRadius: 3 }} />
      </div>
    </div>
  )
}

const FRESHNESS_STYLES: Record<string, { bg: string; fg: string }> = {
  fresh: { bg: '#dcfce7', fg: '#15803d' },
  aging: { bg: '#fef9c3', fg: '#a16207' },
  stale: { bg: '#fee2e2', fg: '#dc2626' },
}

export function FreshnessBadge({
  status, label, compact = false,
}: {
  status: string; label: string; compact?: boolean
}) {
  const style = FRESHNESS_STYLES[status] || FRESHNESS_STYLES.stale
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      fontSize: compact ? 10 : 11,
      fontWeight: 600,
      padding: compact ? '1px 6px' : '2px 8px',
      borderRadius: 4,
      background: style.bg,
      color: style.fg,
      whiteSpace: 'nowrap',
    }}>
      <span style={{ fontSize: compact ? 6 : 8 }}>{'\u25CF'}</span>
      {compact ? status.charAt(0).toUpperCase() + status.slice(1) : label}
    </span>
  )
}

export function RiskBadge({ label, rating, info }: { label: string; rating: string; info?: string }) {
  const NRI_BG: Record<string, string> = {
    'Very High': '#fef2f2',
    'Relatively High': '#fff7ed',
    'Relatively Moderate': '#fefce8',
    'Relatively Low': '#f0fdf4',
    'Very Low': '#f0f9ff',
  }
  const NRI_COLOR: Record<string, string> = {
    'Very High': '#dc2626',
    'Relatively High': '#ea580c',
    'Relatively Moderate': '#ca8a04',
    'Relatively Low': '#16a34a',
    'Very Low': '#2563eb',
  }
  return (
    <span style={{
      fontSize: 12, padding: '4px 8px', borderRadius: 6,
      background: NRI_BG[rating] || '#f1f5f9',
      color: NRI_COLOR[rating] || '#64748b',
      fontWeight: 600, display: 'inline-flex', alignItems: 'center',
    }}>
      {label}: {rating}
      {info && <InfoTip text={info} />}
    </span>
  )
}

// ===== Disposition Badge (Lead Pins) =====

export const DISPOSITION_COLORS: Record<string, string> = {
  not_home: '#94a3b8',
  callback: '#3b82f6',
  interested: '#f59e0b',
  inspection_set: '#8b5cf6',
  contract_signed: '#22c55e',
  not_interested: '#ef4444',
}

export const DISPOSITION_LABELS: Record<string, string> = {
  not_home: 'Not Home',
  callback: 'Callback',
  interested: 'Interested',
  inspection_set: 'Inspection Set',
  contract_signed: 'Contract Signed',
  not_interested: 'Not Interested',
}

export function DispositionBadge({ disposition }: { disposition: string }) {
  const color = DISPOSITION_COLORS[disposition] || '#94a3b8'
  const label = DISPOSITION_LABELS[disposition] || disposition
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '2px 10px',
      borderRadius: '12px',
      fontSize: '12px',
      fontWeight: 600,
      backgroundColor: `${color}20`,
      color: color,
      border: `1px solid ${color}40`,
    }}>
      <span style={{
        width: '8px',
        height: '8px',
        borderRadius: '50%',
        backgroundColor: color,
        flexShrink: 0,
      }} />
      {label}
    </span>
  )
}

// ===== Lead Source Badge =====

export const LEAD_SOURCE_COLORS: Record<string, string> = {
  door_knock: '#6366f1',
  referral: '#22c55e',
  website: '#3b82f6',
  storm_canvass: '#f59e0b',
  other: '#94a3b8',
}

export const LEAD_SOURCE_LABELS: Record<string, string> = {
  door_knock: 'Door Knock',
  referral: 'Referral',
  website: 'Website',
  storm_canvass: 'Storm Canvass',
  other: 'Other',
}

export function LeadSourceBadge({ source }: { source: string }) {
  const color = LEAD_SOURCE_COLORS[source] || '#94a3b8'
  const label = LEAD_SOURCE_LABELS[source] || source
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '2px 10px',
      borderRadius: '12px',
      fontSize: '12px',
      fontWeight: 600,
      backgroundColor: `${color}20`,
      color: color,
      border: `1px solid ${color}40`,
    }}>
      <span style={{
        width: '8px',
        height: '8px',
        borderRadius: '50%',
        backgroundColor: color,
        flexShrink: 0,
      }} />
      {label}
    </span>
  )
}
