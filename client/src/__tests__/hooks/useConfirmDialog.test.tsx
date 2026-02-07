import { describe, it, expect } from 'vitest';
import { renderHook, act, render, screen, fireEvent } from '@testing-library/react';
import { useConfirmDialog } from '../../hooks/useConfirmDialog';

describe('useConfirmDialog', () => {
  it('confirm() returns a promise', () => {
    const { result } = renderHook(() => useConfirmDialog());
    let promise: Promise<boolean> | undefined;

    act(() => {
      promise = result.current.confirm('Are you sure?');
    });

    expect(promise).toBeInstanceOf(Promise);
  });

  it('resolves with true when confirm button is clicked', async () => {
    const { result } = renderHook(() => useConfirmDialog());
    let resolved: boolean | undefined;

    act(() => {
      result.current.confirm('Delete this?', { confirmLabel: 'OK' }).then((v) => { resolved = v; });
    });

    const { getByText } = render(result.current.dialog as any);

    act(() => {
      fireEvent.click(getByText('OK'));
    });

    await vi.waitFor(() => {
      expect(resolved).toBe(true);
    });
  });

  it('resolves with false when cancel button is clicked', async () => {
    const { result } = renderHook(() => useConfirmDialog());
    let resolved: boolean | undefined;

    act(() => {
      result.current.confirm('Delete this?').then((v) => { resolved = v; });
    });

    const { getByText } = render(result.current.dialog as any);

    act(() => {
      fireEvent.click(getByText('Cancel'));
    });

    await vi.waitFor(() => {
      expect(resolved).toBe(false);
    });
  });

  it('shows custom title, message, variant, and labels', () => {
    const { result } = renderHook(() => useConfirmDialog());

    act(() => {
      result.current.confirm('This is dangerous', {
        title: 'Warning!',
        variant: 'danger',
        confirmLabel: 'Yes, delete',
        cancelLabel: 'Keep it',
      });
    });

    const { getByText } = render(result.current.dialog as any);
    expect(getByText('Warning!')).toBeInTheDocument();
    expect(getByText('This is dangerous')).toBeInTheDocument();
    expect(getByText('Yes, delete')).toBeInTheDocument();
    expect(getByText('Keep it')).toBeInTheDocument();
  });
});
