import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { PowerStatusCards } from '../../../components/power/PowerStatusCards';
import type { PowerDemandInfo } from '../../../api/power-management';

const demands = [
  { source: 'a', level: 'low' },
  { source: 'b', level: 'medium' },
] as unknown as PowerDemandInfo[];

describe('PowerStatusCards', () => {
  it('renders all four stat cards including the active-demands count', () => {
    render(
      <PowerStatusCards
        status={{ current_frequency_mhz: 3400 } as never}
        activePreset={{ id: 1, name: 'Balanced', description: 'desc' } as never}
        currentProperty="low"
        demands={demands}
        lastUpdated={new Date(0)}
      />,
    );
    expect(screen.getByText('system:power.statusCards.activePreset')).toBeTruthy();
    expect(screen.getByText('system:power.statusCards.currentProperty')).toBeTruthy();
    expect(screen.getByText('system:power.statusCards.cpuFrequency')).toBeTruthy();
    expect(screen.getByText('system:power.statusCards.activeDemands')).toBeTruthy();
    // active-demands StatCard value is `demands.length`
    expect(screen.getByText('2')).toBeTruthy();
  });
});
