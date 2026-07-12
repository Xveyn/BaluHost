import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import RaidLevelSelectionStep from '../../../components/raid-setup/RaidLevelSelectionStep';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const base = { selectedDisks: ['sda', 'sdb'], selectedRaidLevel: 'raid1', onSelectLevel: vi.fn(), canProceed: true, onBack: vi.fn(), onCancel: vi.fn(), onNext: vi.fn() };

describe('RaidLevelSelectionStep', () => {
  it('only lists RAID levels whose minDisks the selection meets', () => {
    // 2 disks -> raid1 & raid0 (minDisks 2) shown; raid5/6/10 hidden
    render(<RaidLevelSelectionStep {...base} />);
    expect(screen.getByText('RAID 1 (Mirroring)')).toBeInTheDocument();
    expect(screen.getByText('RAID 0 (Striping)')).toBeInTheDocument();
    expect(screen.queryByText('RAID 5 (Parity)')).not.toBeInTheDocument();
  });

  it('shows more levels as disk count grows', () => {
    render(<RaidLevelSelectionStep {...base} selectedDisks={['sda', 'sdb', 'sdc', 'sdd']} />);
    expect(screen.getByText('RAID 5 (Parity)')).toBeInTheDocument();
    expect(screen.getByText('RAID 10 (Mirrored Stripe)')).toBeInTheDocument();
  });

  it('selecting a level fires onSelectLevel', () => {
    const onSelectLevel = vi.fn();
    render(<RaidLevelSelectionStep {...base} onSelectLevel={onSelectLevel} />);
    fireEvent.click(screen.getByText('RAID 0 (Striping)'));
    expect(onSelectLevel).toHaveBeenCalledWith('raid0');
  });
});
