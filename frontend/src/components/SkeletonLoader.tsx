/**
 * Reusable skeleton loading components for RoofIQ.
 *
 * Uses the `.skeleton` CSS class and `var(--skeleton-base)` custom property
 * defined by Agent C in index.css. The `spin` keyframe animation is also
 * defined there and used by MapSpinner.
 */

/** Single zone card placeholder — matches the card view card height/layout */
export function ZoneCardSkeleton() {
  return (
    <div
      style={{
        padding: 12,
        marginBottom: 8,
        borderRadius: 8,
        border: '1px solid var(--border-primary)',
        background: 'var(--card-bg)',
      }}
    >
      {/* Score badge + distance row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div
          className="skeleton"
          style={{
            width: 72,
            height: 22,
            borderRadius: 6,
            background: 'var(--skeleton-base)',
          }}
        />
        <div
          className="skeleton"
          style={{
            width: 48,
            height: 16,
            borderRadius: 4,
            background: 'var(--skeleton-base)',
          }}
        />
      </div>
      {/* Display name line */}
      <div
        className="skeleton"
        style={{
          width: '60%',
          height: 14,
          borderRadius: 4,
          background: 'var(--skeleton-base)',
        }}
      />
    </div>
  )
}

/** Multiple zone card skeletons — used while zone list is loading */
export function ZoneListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <ZoneCardSkeleton key={i} />
      ))}
    </>
  )
}

/** Centered spinner overlay for map loading states */
export function MapSpinner() {
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.15)',
        zIndex: 10,
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          width: 40,
          height: 40,
          border: '4px solid var(--border-primary)',
          borderTopColor: 'var(--accent-blue)',
          borderRadius: '50%',
          animation: 'spin 0.75s linear infinite',
        }}
      />
    </div>
  )
}
