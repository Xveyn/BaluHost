import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import FanCurveGraphControls from '../../../../components/fan-control/fan-details/FanCurveGraphControls';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const base = {
  viewMode: 'chart' as const, onViewModeChange: vi.fn(),
  hasUnsavedChanges: false, isReadOnly: false, onSave: vi.fn(), onDiscard: vi.fn(),
};

describe('FanCurveGraphControls', () => {
  it('switches view mode on toggle click', () => {
    const onViewModeChange = vi.fn();
    render(<FanCurveGraphControls {...base} onViewModeChange={onViewModeChange} />);
    fireEvent.click(screen.getByText('system:fanControl.curve.table'));
    expect(onViewModeChange).toHaveBeenCalledWith('table');
  });

  it('hides save/discard when there are no unsaved changes', () => {
    render(<FanCurveGraphControls {...base} hasUnsavedChanges={false} />);
    expect(screen.queryByText('system:fanControl.curve.save')).not.toBeInTheDocument();
  });

  it('shows save/discard and fires callbacks when there are unsaved changes', () => {
    const onSave = vi.fn();
    const onDiscard = vi.fn();
    render(<FanCurveGraphControls {...base} hasUnsavedChanges onSave={onSave} onDiscard={onDiscard} />);
    fireEvent.click(screen.getByText('system:fanControl.curve.save'));
    fireEvent.click(screen.getByText('system:fanControl.curve.discard'));
    expect(onSave).toHaveBeenCalled();
    expect(onDiscard).toHaveBeenCalled();
  });
});
