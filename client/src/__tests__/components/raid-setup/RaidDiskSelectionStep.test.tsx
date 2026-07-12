import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { AvailableDisk } from '../../../api/raid';
import RaidDiskSelectionStep from '../../../components/raid-setup/RaidDiskSelectionStep';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const disk = (name: string): AvailableDisk => ({
  name, size_bytes: 5 * 1024 ** 3, model: 'Dev Disk', is_partitioned: true,
  partitions: [`${name}1`], in_raid: false, is_os_disk: false,
});
const base = { freeDisks: [disk('sda'), disk('sdb')], selectedDisks: [], onToggleDisk: vi.fn(), canProceed: false, onCancel: vi.fn(), onNext: vi.fn() };

describe('RaidDiskSelectionStep', () => {
  it('shows the empty state when there are no free disks', () => {
    render(<RaidDiskSelectionStep {...base} freeDisks={[]} />);
    expect(screen.getByText('raidWizard.selectDisks.noDisks')).toBeInTheDocument();
  });

  it('toggling a disk fires onToggleDisk', () => {
    const onToggleDisk = vi.fn();
    render(<RaidDiskSelectionStep {...base} onToggleDisk={onToggleDisk} />);
    fireEvent.click(screen.getByText('/dev/sda'));
    expect(onToggleDisk).toHaveBeenCalledWith('sda');
  });

  it('Next is disabled when canProceed is false and enabled when true', () => {
    const { rerender } = render(<RaidDiskSelectionStep {...base} canProceed={false} />);
    expect(screen.getByText('raidWizard.next')).toBeDisabled();
    rerender(<RaidDiskSelectionStep {...base} canProceed />);
    expect(screen.getByText('raidWizard.next')).not.toBeDisabled();
  });
});
