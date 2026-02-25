function LoadingSpinner() {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100vh',
      width: '100%',
    }}>
      <div style={{
        width: 40,
        height: 40,
        border: '3px solid var(--border-primary)',
        borderTopColor: 'var(--accent-blue)',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
    </div>
  )
}

export default LoadingSpinner
