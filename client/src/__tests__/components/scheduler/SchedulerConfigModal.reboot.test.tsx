import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
      enabled: true, computed_from_parameters: true,
      next_due_at: '2026-09-13T02:00:00Z', in_core_uptime: false,
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

  it('asks the backend with the values currently in the form', async () => {
    // Ohne die Parameter rechnet der Endpunkt mit der GESPEICHERTEN
    // Konfiguration - und die gibt es beim Ersteinrichten noch gar nicht
    // (Feature standardmaessig aus). Die Warnung koennte in genau dem Moment,
    // fuer den sie existiert, nie erscheinen.
    render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
      onClose={() => {}} onSave={async () => true} />);
    await waitFor(() => expect(getRebootPreview).toHaveBeenCalled());
    expect(getRebootPreview).toHaveBeenCalledWith({
      weekday: 6, time: '04:00', retry_window_hours: 6,
    });
  });

  it('re-asks with the new weekday when the selection changes', async () => {
    const user = userEvent.setup();
    render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
      onClose={() => {}} onSave={async () => true} />);
    await waitFor(() => expect(getRebootPreview).toHaveBeenCalled());

    await user.selectOptions(screen.getByTestId('reboot-weekday'), '2');

    await waitFor(() => expect(getRebootPreview).toHaveBeenLastCalledWith({
      weekday: 2, time: '04:00', retry_window_hours: 6,
    }));
  });

  it('warns that the reboot will never run when the window outlasts the retry window', async () => {
    getRebootPreview.mockResolvedValue({
      enabled: true, computed_from_parameters: true,
      next_due_at: '2026-09-14T08:00:00Z', in_core_uptime: true,
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
      enabled: true, computed_from_parameters: true,
      next_due_at: '2026-09-14T08:00:00Z', in_core_uptime: true,
      window_label: 'Vormittag', window_ends_at: '2026-09-14T10:00:00Z',
      retry_deadline_at: '2026-09-14T20:00:00Z', reachable: true,
    });
    render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
      onClose={() => {}} onSave={async () => true} />);
    const warning = await screen.findByTestId('reboot-core-uptime-warning');
    expect(warning.textContent).toContain('configModal.reboot.warningDeferred');
  });

  describe('retry window field while typing (#624)', () => {
    const neverReachable = {
      enabled: true, computed_from_parameters: true,
      next_due_at: '2026-09-14T08:00:00Z', in_core_uptime: true,
      window_label: 'Wochentags', window_ends_at: '2026-09-14T20:00:00Z',
      retry_deadline_at: '2026-09-14T14:00:00Z', reachable: false,
    };

    beforeEach(() => {
      // Wie das Backend: gueltig ist 1-24, alles andere ist ein 422.
      getRebootPreview.mockImplementation((params: { retry_window_hours: number }) =>
        Number.isInteger(params.retry_window_hours)
          && params.retry_window_hours >= 1 && params.retry_window_hours <= 24
          ? Promise.resolve(neverReachable)
          : Promise.reject(new Error('422')));
    });

    const requestedHours = () =>
      getRebootPreview.mock.calls.map(([params]) => params.retry_window_hours);

    it('keeps the warning when the field is emptied', async () => {
      const user = userEvent.setup();
      render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
        onClose={() => {}} onSave={async () => true} />);
      await screen.findByTestId('reboot-core-uptime-warning');

      await user.clear(screen.getByTestId('reboot-retry'));
      // Dem (frueheren) 422 Zeit geben, die Warnung abzuraeumen.
      await new Promise((resolve) => setTimeout(resolve, 0));

      expect(screen.getByTestId('reboot-core-uptime-warning')).toBeInTheDocument();
      expect(requestedHours()).toEqual([6]);
    });

    it('shows the emptied field as empty, not as 0', async () => {
      const user = userEvent.setup();
      render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
        onClose={() => {}} onSave={async () => true} />);
      await screen.findByTestId('reboot-core-uptime-warning');

      await user.clear(screen.getByTestId('reboot-retry'));

      expect(screen.getByTestId('reboot-retry')).toHaveValue(null);
    });

    it('asks again once a valid number stands in the field', async () => {
      const user = userEvent.setup();
      render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
        onClose={() => {}} onSave={async () => true} />);
      await screen.findByTestId('reboot-core-uptime-warning');

      const field = screen.getByTestId('reboot-retry');
      await user.clear(field);
      await user.type(field, '12');

      await waitFor(() => expect(getRebootPreview).toHaveBeenLastCalledWith({
        weekday: 6, time: '04:00', retry_window_hours: 12,
      }));
      // "1" auf dem Weg zur "12" ist selbst gueltig und darf gefragt werden;
      // eine 0 oder ein leerer Wert nie.
      expect(requestedHours().every((h) => h >= 1 && h <= 24)).toBe(true);
    });

    it('does not ask for a number outside 1-24', async () => {
      const user = userEvent.setup();
      render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
        onClose={() => {}} onSave={async () => true} />);
      await screen.findByTestId('reboot-core-uptime-warning');

      const field = screen.getByTestId('reboot-retry');
      await user.clear(field);
      await user.type(field, '99');
      await new Promise((resolve) => setTimeout(resolve, 0));

      // 6 beim Oeffnen, 9 als gueltiger Zwischenstand - die 99 nicht.
      expect(requestedHours()).toEqual([6, 9]);
      expect(screen.getByTestId('reboot-core-uptime-warning')).toBeInTheDocument();
    });

    it('names the hours the warning was computed for, not the half-typed ones', async () => {
      const user = userEvent.setup();
      render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
        onClose={() => {}} onSave={async () => true} />);
      await screen.findByTestId('reboot-core-uptime-warning');

      await user.clear(screen.getByTestId('reboot-retry'));

      expect(screen.getByTestId('reboot-core-uptime-warning').textContent)
        .toContain('"retryHours":6');
    });

    it('refuses to save while the field holds no valid number', async () => {
      const user = userEvent.setup();
      const onSave = vi.fn(async () => true);
      render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
        onClose={() => {}} onSave={onSave} />);
      await screen.findByTestId('reboot-core-uptime-warning');

      await user.clear(screen.getByTestId('reboot-retry'));
      await user.click(screen.getByText('common:buttons.save'));

      expect(onSave).not.toHaveBeenCalled();
      expect(screen.getByText('scheduler:configModal.reboot.retryHoursInvalid')).toBeInTheDocument();
    });

    it('saves the typed number as a number', async () => {
      const user = userEvent.setup();
      const onSave = vi.fn(async () => true);
      render(<SchedulerConfigModal scheduler={rebootScheduler} isOpen
        onClose={() => {}} onSave={onSave} />);
      await screen.findByTestId('reboot-core-uptime-warning');

      const field = screen.getByTestId('reboot-retry');
      await user.clear(field);
      await user.type(field, '12');
      await user.click(screen.getByText('common:buttons.save'));

      expect(onSave).toHaveBeenCalledWith('system_reboot', {
        is_enabled: true,
        extra_config: {
          weekday: 6, time: '04:00', retry_window_hours: 12, warning_lead_minutes: 10,
        },
      });
    });
  });
});
