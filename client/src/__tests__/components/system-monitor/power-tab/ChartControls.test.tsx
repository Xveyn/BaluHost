import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }));
vi.mock('../../../../lib/dateUtils', () => ({
  localRangeToUtcIso: vi.fn(() => ({ startIso: 'S', endIso: 'E' })),
}));

import toast from 'react-hot-toast';
import { ChartModePeriodControls } from '../../../../components/system-monitor/power-tab/ChartModePeriodControls';
import { CustomRangePicker } from '../../../../components/system-monitor/power-tab/CustomRangePicker';

describe('ChartModePeriodControls', () => {
  it('renders mode + period buttons and the customRange node', () => {
    render(
      <ChartModePeriodControls
        chartMode="cumulative"
        onModeChange={vi.fn()}
        cumulativePeriod="today"
        onPeriodChange={vi.fn()}
        customRange={<div>custom-range-slot</div>}
      />
    );

    expect(screen.getByText('monitor.power.modeCumulative')).toBeTruthy();
    expect(screen.getByText('monitor.power.modeInstant')).toBeTruthy();
    expect(screen.getByText('monitor.power.periodToday')).toBeTruthy();
    expect(screen.getByText('monitor.power.periodWeek')).toBeTruthy();
    expect(screen.getByText('monitor.power.periodMonth')).toBeTruthy();
    expect(screen.getByText('custom-range-slot')).toBeTruthy();
  });

  it('fires onPeriodChange("week") when the week button is clicked', () => {
    const onPeriodChange = vi.fn();
    render(
      <ChartModePeriodControls
        chartMode="cumulative"
        onModeChange={vi.fn()}
        cumulativePeriod="today"
        onPeriodChange={onPeriodChange}
        customRange={<div>custom-range-slot</div>}
      />
    );

    fireEvent.click(screen.getByText('monitor.power.periodWeek'));
    expect(onPeriodChange).toHaveBeenCalledWith('week');
  });

  it('fires onModeChange("instant") when the instant button is clicked', () => {
    const onModeChange = vi.fn();
    render(
      <ChartModePeriodControls
        chartMode="cumulative"
        onModeChange={onModeChange}
        cumulativePeriod="today"
        onPeriodChange={vi.fn()}
        customRange={<div>custom-range-slot</div>}
      />
    );

    fireEvent.click(screen.getByText('monitor.power.modeInstant'));
    expect(onModeChange).toHaveBeenCalledWith('instant');
  });
});

describe('CustomRangePicker', () => {
  it('opens the popover when the Custom button is clicked', () => {
    render(<CustomRangePicker active={false} onApply={vi.fn()} />);

    expect(screen.queryByText('monitor.power.customApply')).toBeNull();
    fireEvent.click(screen.getByText('monitor.power.periodCustom'));
    expect(screen.getByText('monitor.power.customApply')).toBeTruthy();
  });

  it('shows a toast error and does not call onApply when drafts are empty', () => {
    const onApply = vi.fn();
    render(<CustomRangePicker active={false} onApply={onApply} />);

    fireEvent.click(screen.getByText('monitor.power.periodCustom'));
    fireEvent.click(screen.getByText('monitor.power.customApply'));

    expect(toast.error).toHaveBeenCalledWith('monitor.power.customInvalidRange');
    expect(onApply).not.toHaveBeenCalled();
  });

  it('calls onApply with the ISO range returned by localRangeToUtcIso once both dates are set', () => {
    const onApply = vi.fn();
    const { container } = render(<CustomRangePicker active={false} onApply={onApply} />);

    fireEvent.click(screen.getByText('monitor.power.periodCustom'));
    const dateInputs = container.querySelectorAll('input[type="date"]');
    expect(dateInputs.length).toBe(2);
    fireEvent.change(dateInputs[0], { target: { value: '2026-07-01' } });
    fireEvent.change(dateInputs[1], { target: { value: '2026-07-05' } });
    fireEvent.click(screen.getByText('monitor.power.customApply'));

    expect(onApply).toHaveBeenCalledWith('S', 'E');
  });
});
