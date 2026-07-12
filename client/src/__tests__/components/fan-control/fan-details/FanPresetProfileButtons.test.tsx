import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { FanCurveProfile } from '../../../../api/fan-control';
import FanPresetProfileButtons from '../../../../components/fan-control/fan-details/FanPresetProfileButtons';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const base = {
  isReadOnly: false, systemProfiles: [], userProfiles: [],
  showMoreProfiles: false, onToggleMore: vi.fn(),
  onApplyPreset: vi.fn(), onApplyProfile: vi.fn(),
};

describe('FanPresetProfileButtons', () => {
  it('renders nothing when read-only', () => {
    const { container } = render(<FanPresetProfileButtons {...base} isReadOnly />);
    expect(container.firstChild).toBeNull();
  });

  it('falls back to hardcoded presets when there are no system profiles', () => {
    const onApplyPreset = vi.fn();
    render(<FanPresetProfileButtons {...base} onApplyPreset={onApplyPreset} />);
    fireEvent.click(screen.getByText('system:fanControl.presets.silent'));
    expect(onApplyPreset).toHaveBeenCalledWith('silent');
  });

  it('renders a system profile button and fires onApplyProfile', () => {
    const p: FanCurveProfile = { id: 1, name: 'balanced', curve_points: [], is_system: true };
    const onApplyProfile = vi.fn();
    render(<FanPresetProfileButtons {...base} systemProfiles={[p]} onApplyProfile={onApplyProfile} />);
    fireEvent.click(screen.getByText('Balanced'));
    expect(onApplyProfile).toHaveBeenCalledWith(p);
  });
});
