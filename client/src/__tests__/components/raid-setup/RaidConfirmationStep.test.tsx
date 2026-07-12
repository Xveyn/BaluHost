import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import RaidConfirmationStep from '../../../components/raid-setup/RaidConfirmationStep';
import { RAID_LEVELS } from '../../../components/raid-setup/raidLevels';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const base = {
  arrayName: 'md1', onArrayNameChange: vi.fn(), isArrayNameValid: true,
  raidInfo: RAID_LEVELS[0], capacity: '5 GB', selectedDisks: ['sda', 'sdb'],
  busy: false, onBack: vi.fn(), onCancel: vi.fn(), onSubmit: vi.fn(),
};

describe('RaidConfirmationStep', () => {
  it('renders capacity, disk chips and the create button', () => {
    render(<RaidConfirmationStep {...base} />);
    expect(screen.getByText('5 GB')).toBeInTheDocument();
    expect(screen.getByText('/dev/sda')).toBeInTheDocument();
    expect(screen.getByText('raidWizard.createArray')).toBeInTheDocument();
  });

  it('typing in the name input fires onArrayNameChange', () => {
    const onArrayNameChange = vi.fn();
    render(<RaidConfirmationStep {...base} onArrayNameChange={onArrayNameChange} />);
    fireEvent.change(screen.getByPlaceholderText('md0'), { target: { value: 'md2' } });
    expect(onArrayNameChange).toHaveBeenCalledWith('md2');
  });

  it('disables submit when the name is invalid', () => {
    render(<RaidConfirmationStep {...base} isArrayNameValid={false} />);
    expect(screen.getByText('raidWizard.createArray')).toBeDisabled();
  });

  it('shows the creating label and disables submit while busy', () => {
    render(<RaidConfirmationStep {...base} busy />);
    expect(screen.getByText('raidWizard.creating')).toBeDisabled();
  });
});
