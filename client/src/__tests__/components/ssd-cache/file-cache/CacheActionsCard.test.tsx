import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CacheActionsCard } from '../../../../components/ssd-cache/file-cache/CacheActionsCard';

describe('CacheActionsCard', () => {
  it('fires each action callback on its button', () => {
    const onTriggerEviction = vi.fn(), onClearCache = vi.fn(), onRefresh = vi.fn();
    render(<CacheActionsCard actionLoading={false}
      onTriggerEviction={onTriggerEviction} onClearCache={onClearCache} onRefresh={onRefresh} />);
    fireEvent.click(screen.getByText('Trigger Eviction'));
    fireEvent.click(screen.getByText('Clear Cache'));
    fireEvent.click(screen.getByText('Refresh'));
    expect(onTriggerEviction).toHaveBeenCalledTimes(1);
    expect(onClearCache).toHaveBeenCalledTimes(1);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
  it('disables all buttons while an action is loading', () => {
    render(<CacheActionsCard actionLoading={true}
      onTriggerEviction={() => {}} onClearCache={() => {}} onRefresh={() => {}} />);
    for (const label of ['Trigger Eviction', 'Clear Cache', 'Refresh']) {
      expect(screen.getByText(label).closest('button')).toBeDisabled();
    }
  });
});
