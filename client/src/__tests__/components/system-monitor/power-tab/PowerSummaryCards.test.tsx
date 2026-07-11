import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string, fallback?: string) => fallback ?? k }) }));
vi.mock('../../../../lib/formatters', () => ({ formatNumber: (value: number, decimals: number) => value.toFixed(decimals) }));

import { PowerSummaryCards } from '../../../../components/system-monitor/power-tab/PowerSummaryCards';

describe('PowerSummaryCards', () => {
  it('renders current power, online count, and device count', () => {
    render(
      <PowerSummaryCards totalCurrentPower={42.4} onlineCount={2} deviceCount={3} />,
    );
    expect(screen.getByText('42.4')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
    expect(screen.getByText('/ 3')).toBeTruthy();
  });
});
