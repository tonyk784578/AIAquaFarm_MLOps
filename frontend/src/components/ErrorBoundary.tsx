/**
 * Global React error boundary.
 *
 * React class components are still the only way to catch render-time errors
 * in a subtree (hooks have no equivalent). Wrap the entire app in App.tsx so
 * a single broken component never paints a blank white screen.
 *
 * The fallback UI is deliberately minimal — it does not depend on any other
 * component or Tailwind class names (just inline styles + CSS vars defined
 * in global.css), so it still renders even when the design system fails.
 */
import { Component, type ErrorInfo, type PropsWithChildren, type ReactNode } from 'react'

interface State {
  error: Error | null
  info: ErrorInfo | null
}

interface Props {
  /** Custom fallback UI; receives the captured error + a reset callback. */
  fallback?: (props: { error: Error; reset: () => void }) => ReactNode
  /** Side-effect hook (telemetry / logging). */
  onError?: (error: Error, info: ErrorInfo) => void
}

export class ErrorBoundary extends Component<PropsWithChildren<Props>, State> {
  state: State = { error: null, info: null }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.setState({ info })
    // Console first — visible in dev tools and grep-able from container logs.
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error, info.componentStack)
    this.props.onError?.(error, info)
  }

  reset = (): void => {
    this.setState({ error: null, info: null })
  }

  render(): ReactNode {
    const { error } = this.state
    if (!error) return this.props.children

    if (this.props.fallback) {
      return this.props.fallback({ error, reset: this.reset })
    }

    return (
      <div
        role="alert"
        style={{
          padding: '32px',
          maxWidth: '640px',
          margin: '64px auto',
          borderRadius: '12px',
          border: '1px solid var(--bg-border, #e5e7eb)',
          backgroundColor: 'var(--bg-surface, #ffffff)',
          color: 'var(--text-primary, #111827)',
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '8px' }}>
          페이지 표시 중 오류가 발생했습니다
        </h2>
        <p style={{ color: 'var(--text-muted, #6b7280)', fontSize: '14px', marginBottom: '16px' }}>
          이 화면은 안전한 폴백입니다. 새로고침해도 같은 오류가 반복되면 운영자에게 알려주세요.
        </p>

        <pre
          style={{
            fontSize: '12px',
            backgroundColor: 'var(--bg-elevated, #f3f4f6)',
            padding: '12px',
            borderRadius: '8px',
            overflowX: 'auto',
            whiteSpace: 'pre-wrap',
            color: 'var(--danger, #b91c1c)',
            marginBottom: '16px',
          }}
        >
          {error.name}: {error.message}
        </pre>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={this.reset}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: 'var(--info, #2563eb)',
              color: 'white',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            다시 시도
          </button>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: '1px solid var(--bg-border, #e5e7eb)',
              backgroundColor: 'transparent',
              color: 'var(--text-primary, #111827)',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            새로고침
          </button>
        </div>
      </div>
    )
  }
}

export default ErrorBoundary
