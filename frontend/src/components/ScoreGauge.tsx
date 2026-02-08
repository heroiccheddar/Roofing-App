interface ScoreGaugeProps {
  score: number
  size?: 'small' | 'medium' | 'large'
}

function ScoreGauge({ score, size = 'medium' }: ScoreGaugeProps) {
  // TODO: Implement in WP 4.1
  // - Visual gauge/meter showing score 0-100
  // - Color-coded (red = high, yellow = medium, green = low)
  // - Different sizes for different contexts
  // - Optional: show numeric value

  const sizeMap = {
    small: '40px',
    medium: '80px',
    large: '120px',
  }

  return (
    <div style={{ width: sizeMap[size], height: sizeMap[size], border: '2px solid #ccc', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span>{score}</span>
    </div>
  )
}

export default ScoreGauge
