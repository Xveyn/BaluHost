import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { VclMaintenanceCard } from '../../../../components/vcl/vcl-settings/VclMaintenanceCard';

describe('VclMaintenanceCard', () => {
  it('fires each callback on its button', () => {
    const onDryRunCleanup = vi.fn(), onTriggerCleanup = vi.fn(), onRefresh = vi.fn();
    render(<VclMaintenanceCard actionLoading={false}
      onDryRunCleanup={onDryRunCleanup} onTriggerCleanup={onTriggerCleanup} onRefresh={onRefresh} />);
    fireEvent.click(screen.getByText('vcl.maintenance.dryRunCleanup'));
    fireEvent.click(screen.getByText('vcl.maintenance.triggerCleanup'));
    fireEvent.click(screen.getByText('vcl.maintenance.refreshStats'));
    expect(onDryRunCleanup).toHaveBeenCalledTimes(1);
    expect(onTriggerCleanup).toHaveBeenCalledTimes(1);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
  it('disables all buttons while an action is loading', () => {
    render(<VclMaintenanceCard actionLoading={true}
      onDryRunCleanup={() => {}} onTriggerCleanup={() => {}} onRefresh={() => {}} />);
    for (const k of ['vcl.maintenance.dryRunCleanup', 'vcl.maintenance.triggerCleanup', 'vcl.maintenance.refreshStats']) {
      expect(screen.getByText(k).closest('button')).toBeDisabled();
    }
  });
});
