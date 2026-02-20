import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ErrorBoundary } from '../../components/ErrorBoundary';

// Component that throws an error on render
function ThrowingComponent({ error }: { error: Error }): never {
  throw error;
}

const originalConsoleError = console.error;

describe('ErrorBoundary', () => {
  beforeEach(() => {
    console.error = vi.fn();
  });

  afterEach(() => {
    console.error = originalConsoleError;
  });

  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <div>Child content</div>
      </ErrorBoundary>
    );

    expect(screen.getByText('Child content')).toBeInTheDocument();
  });

  it('renders fallback UI when an error is thrown', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent error={new Error('Test error')} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Test error')).toBeInTheDocument();
  });

  it('shows "Reload page" button', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent error={new Error('Crash')} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Reload page')).toBeInTheDocument();
  });

  it('shows default message when error has no message', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent error={new Error('')} />
      </ErrorBoundary>
    );

    expect(screen.getByText('An unexpected error occurred')).toBeInTheDocument();
  });

  it('calls console.error via componentDidCatch', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent error={new Error('caught error')} />
      </ErrorBoundary>
    );

    expect(console.error).toHaveBeenCalled();
  });

  it('handles dynamic import errors by setting sessionStorage', () => {
    // Mock sessionStorage
    const getItemMock = vi.fn().mockReturnValue(null);
    const setItemMock = vi.fn();
    Object.defineProperty(window, 'sessionStorage', {
      value: { getItem: getItemMock, setItem: setItemMock },
      writable: true,
      configurable: true,
    });

    // Mock window.location.reload
    const reloadMock = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { ...window.location, reload: reloadMock },
      writable: true,
      configurable: true,
    });

    render(
      <ErrorBoundary>
        <ThrowingComponent
          error={new Error('Failed to fetch dynamically imported module /chunk-abc123.js')}
        />
      </ErrorBoundary>
    );

    expect(setItemMock).toHaveBeenCalledWith('chunk-reload', '1');
  });
});
