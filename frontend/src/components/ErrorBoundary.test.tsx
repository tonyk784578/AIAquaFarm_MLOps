/**
 * ErrorBoundary tests — verify catch behaviour and reset semantics.
 *
 * Suppresses the noisy React error log during the expected-failure tests
 * so the suite output stays readable.
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ErrorBoundary from './ErrorBoundary'

function Boom({ message = 'boom' }: { message?: string }) {
  throw new Error(message)
}

let consoleErrorSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  // React logs a noisy "Consider adding an error boundary..." line whenever a
  // boundary catches an error. Silence it for the duration of the test.
  consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  consoleErrorSpy.mockRestore()
})

describe('ErrorBoundary', () => {
  it('renders children when no error is thrown', () => {
    render(
      <ErrorBoundary>
        <p>healthy content</p>
      </ErrorBoundary>,
    )
    expect(screen.getByText('healthy content')).toBeInTheDocument()
  })

  it('renders default fallback when a child throws', () => {
    render(
      <ErrorBoundary>
        <Boom message="render failure" />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/페이지 표시 중 오류/)).toBeInTheDocument()
    expect(screen.getByText(/render failure/)).toBeInTheDocument()
  })

  it('invokes onError callback with the captured error', () => {
    const onError = vi.fn()
    render(
      <ErrorBoundary onError={onError}>
        <Boom message="hook me" />
      </ErrorBoundary>,
    )
    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error)
    expect((onError.mock.calls[0][0] as Error).message).toBe('hook me')
  })

  it('renders custom fallback prop when provided', () => {
    render(
      <ErrorBoundary fallback={({ error }) => <p>custom: {error.message}</p>}>
        <Boom message="x" />
      </ErrorBoundary>,
    )
    expect(screen.getByText('custom: x')).toBeInTheDocument()
  })

  it('reset clears the error and renders children again', () => {
    // Toggle state so the second render does NOT throw.
    let shouldThrow = true
    function Maybe() {
      if (shouldThrow) throw new Error('first time')
      return <p>recovered</p>
    }

    const { rerender } = render(
      <ErrorBoundary>
        <Maybe />
      </ErrorBoundary>,
    )
    expect(screen.getByText(/first time/)).toBeInTheDocument()

    // Flip the flag, then click "다시 시도" — boundary resets and re-renders.
    shouldThrow = false
    fireEvent.click(screen.getByText('다시 시도'))
    rerender(
      <ErrorBoundary>
        <Maybe />
      </ErrorBoundary>,
    )
    expect(screen.getByText('recovered')).toBeInTheDocument()
  })
})
