/**
 * Shared formatting utilities for zone score display.
 *
 * Extracted from ZonePanel to share with ZoneDetail page.
 */

/** Format a number as an ordinal (1st, 2nd, 3rd, etc.) */
export function ordinal(n: number): string {
  const r = Math.round(n)
  const s = ['th', 'st', 'nd', 'rd']
  const v = r % 100
  return r + (s[(v - 20) % 10] || s[v] || s[0])
}

/** Linearly interpolate between two hex colors. */
export function lerpColor(a: string, b: string, t: number): string {
  const parse = (hex: string) => [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ]
  const ca = parse(a), cb = parse(b)
  const r = Math.round(ca[0] + (cb[0] - ca[0]) * t)
  const g = Math.round(ca[1] + (cb[1] - ca[1]) * t)
  const bl = Math.round(ca[2] + (cb[2] - ca[2]) * t)
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${bl.toString(16).padStart(2, '0')}`
}

/** Return background + text color for a composite score (0-100).
 *
 * 21 color stops (every 5 points) with distinct color families.
 * Extra differentiation in the 80-100 range where lead quality matters most.
 *
 *   0-15  -> grays / steel        (skip band)
 *  20-25  -> blue / indigo        (cool low-end)
 *  30-45  -> violet / purple      (cool band)
 *  50-65  -> teal / emerald       (warm band)
 *  70-80  -> lime / yellow / amber (hot low-end)
 *  85-100 -> orange -> red -> crimson -> magenta (hot high-end)
 */
export function scoreColor(score: number): { bg: string; fg: string } {
  const s = Math.max(0, Math.min(100, score))

  const stops: [number, string, string][] = [
    [  0, '#f1f5f9', '#64748b'],
    [  5, '#f0f1f3', '#5b6270'],
    [ 10, '#e8edf4', '#475876'],
    [ 15, '#e2e8f0', '#3b4f7a'],
    [ 20, '#dbeafe', '#1e40af'],
    [ 25, '#e0e7ff', '#4338ca'],
    [ 30, '#ede9fe', '#6d28d9'],
    [ 35, '#f3e8ff', '#7e22ce'],
    [ 40, '#fae8ff', '#a21caf'],
    [ 45, '#fce7f3', '#9d174d'],
    [ 50, '#ccfbf1', '#0f766e'],
    [ 55, '#cffafe', '#0e7490'],
    [ 60, '#d1fae5', '#047857'],
    [ 65, '#dcfce7', '#15803d'],
    [ 70, '#ecfccb', '#4d7c0f'],
    [ 75, '#fef9c3', '#a16207'],
    [ 80, '#fef3c7', '#b45309'],
    [ 85, '#ffedd5', '#c2410c'],
    [ 90, '#fee2e2', '#dc2626'],
    [ 95, '#ffe4e6', '#be123c'],
    [100, '#fae8ff', '#86198f'],
  ]

  let lo = stops[0], hi = stops[stops.length - 1]
  for (let i = 0; i < stops.length - 1; i++) {
    if (s >= stops[i][0] && s <= stops[i + 1][0]) {
      lo = stops[i]
      hi = stops[i + 1]
      break
    }
  }

  const t = hi[0] === lo[0] ? 0 : (s - lo[0]) / (hi[0] - lo[0])
  return {
    bg: lerpColor(lo[1], hi[1], t),
    fg: lerpColor(lo[2], hi[2], t),
  }
}
