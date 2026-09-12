import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { SchedulerConfigModal } from '../../../components/scheduler/SchedulerConfigModal';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, opts?: Record<string, unknown>) =>
    opts ? `${key} ${JSON.stringify(opts)}` : key }),
}));

const getRebootPreview = vi.fn();
vi.mock('../../../api/schedulers', () => ({
  getRebootPreview: (...args: unknown[]) => getRebootPreview(...args),
}));

const rebootScheduler = {
  name: 'system_reboot',
  display_name: 'Geplanter Neustart',
  description: '',
  is_running: false,
  is_enabled: true,
  interval_seconds: 604800,
  interval_display: 'Sonntag 04:00',
  can_run_manually: false,
  extra_config: { weekday: 6, time: '04:00', retry_window_hours: 6, warning_lead_minutes: 10 },
} as never;

describe('SchedulerConfigModal — system_reboot', () => {
  beforeEach(() => {
    getRebootPreview.mockReset();
    getRebootPreview.mockResolvedValue({
      enabled: true, next_due_at: '2026-09-13T02:00:00Z', in_core_uptime: false,
      window_label: null, window_ends_at: null,
      retry_deadline_at: '2026-09-13T08:00:00Z', reachable: true,
    });
  });

  it('shows weekday and time instead of the interval controls', async () => {
    render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
      onClose={() => {}} onSave={async () => true} />);
    expect(await screen.findByTestId('reboot-weekday')).toBeInTheDocument();
    expect(screen.getByTestId('reboot-time')).toBeInTheDocument();
    expect(screen.queryByTestId('interval-value')).not.toBeInTheDocument();
  });

  it('renders no warning without a collision', async () => {
    render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
      onClose={() => {}} onSave={async () => true} />);
    await waitFor(() => expect(getRebootPreview).toHaveBeenCalled());
    expect(screen.queryByTestId('reboot-core-uptime-warning')).not.toBeInTheDocument();
  });

  it('warns that the reboot will never run when the window outlasts the retry window', async () => {
    getRebootPreview.mockResolvedValue({
      enabled: true, next_due_at: '2026-09-14T08:00:00Z', in_core_uptime: true,
      window_label: 'Wochentags', window_ends_at: '2026-09-14T20:00:00Z',
      retry_deadline_at: '2026-09-14T14:00:00Z', reachable: false,
    });
    render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
      onClose={() => {}} onSave={async () => true} />);
    const warning = await screen.findByTestId('reboot-core-uptime-warning');
    expect(warning.textContent).toContain('configModal.reboot.warningNever');
  });

  it('warns more mildly when the reboot is caught up after the window', async () => {
    getRebootPreview.mockResolvedValue({
      enabled: true, next_due_at: '2026-09-14T08:00:00Z', in_core_uptime: true,
      window_label: 'Vormittag', window_ends_at: '2026-09-14T10:00:00Z',
      retry_deadline_at: '2026-09-14T20:00:00Z', reachable: true,
    });
    render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
      onClose={() => {}} onSave={async () => true} />);
    const warning = await screen.findByTestId('reboot-core-uptime-warning');
    expect(warning.textContent).toContain('configModal.reboot.warningDeferred');
  });
});
