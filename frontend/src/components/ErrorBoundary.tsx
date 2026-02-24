import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

/**
 * React error boundary that catches rendering errors in its child tree.
 * Shows a styled error message with a Retry button that resets state.
 */
class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface the error to the console so it's not swallowed
    console.error('[ErrorBoundary] Caught rendering error:', error, info.componentStack)
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div
          role="alert"
          style={{
            padding: 16,
            margin: 8,
            borderRadius: 8,
            background: 'var(--error-bg)',
            color: 'var(--error-text)',
            border: '1px solid var(--accent-red)',
          }}
        >
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>
            Something went wrong
          </div>
          {this.state.error && (
            <div style={{ fontSize: 12, marginBottom: 12, opacity: 0.8, fontFamily: 'monospace', wordBreak: 'break-word' }}>
              {this.state.error.message}
            </div>
          )}
          <button
            onClick={this.handleRetry}
            style={{
              padding: '6px 14px',
              borderRadius: 6,
              border: 'none',
              background: 'var(--accent-blue)',
              color: '#fff',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
