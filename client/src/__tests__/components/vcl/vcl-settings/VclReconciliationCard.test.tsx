import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReconciliationPreview } from '../../../../types/vcl';
import { VclReconciliationCard } from '../../../../components/vcl/vcl-settings/VclReconciliationCard';

const preview = (over: Partial<ReconciliationPreview> = {}): ReconciliationPreview => ({
  total_mismatches: 0, mismatches: [], affected_users: [], ...over,
});
const base = { reconLoading: false, forceOverQuota: false, onScan: () => {}, onForceChange: () => {}, onApply: () => {} };

describe('VclReconciliationCard', () => {
  it('fires onScan when Scan for Mismatches is clicked', () => {
    const onScan = vi.fn();
    render(<VclReconciliationCard {...base} reconPreview={null} onScan={onScan} />);
    fireEvent.click(screen.getByText('Scan for Mismatches'));
    expect(onScan).toHaveBeenCalledTimes(1);
  });
  it('hides Apply + force checkbox when there are no mismatches', () => {
    render(<VclReconciliationCard {...base} reconPreview={preview({ total_mismatches: 0 })} />);
    expect(screen.queryByText(/^Apply \(/)).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
  it('shows Apply with the mismatch count when there are mismatches', () => {
    render(<VclReconciliationCard {...base} reconPreview={preview({
      total_mismatches: 2,
      mismatches: [
        { file_id: 1, file_path: '/a/b.txt', version_id: 11, version_number: 3, current_version_user_id: 1, current_version_username: 'alice', current_file_owner_id: 2, current_file_owner_username: 'bob', compressed_size: 100 },
      ],
      affected_users: [{ user_id: 2, username: 'bob', quota_delta: 100, current_usage: 0, max_size: 1000, would_exceed_quota: false }],
    })} />);
    expect(screen.getByText('Apply (2 versions)')).toBeInTheDocument();
    expect(screen.getByRole('checkbox')).toBeInTheDocument();
    expect(screen.getByText('b.txt')).toBeInTheDocument();
  });
  it('fires onForceChange when the force checkbox toggles', () => {
    const onForceChange = vi.fn();
    render(<VclReconciliationCard {...base} onForceChange={onForceChange}
      reconPreview={preview({ total_mismatches: 1, mismatches: [], affected_users: [] })} />);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(onForceChange).toHaveBeenCalledWith(true);
  });
});
