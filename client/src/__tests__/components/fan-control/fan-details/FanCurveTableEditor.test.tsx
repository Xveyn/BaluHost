import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { FanCurvePoint } from '../../../../api/fan-control';
import FanCurveTableEditor from '../../../../components/fan-control/fan-details/FanCurveTableEditor';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const points: FanCurvePoint[] = [{ temp: 40, pwm: 40 }, { temp: 60, pwm: 80 }];
const base = {
  curvePoints: points, canEdit: true, minPwm: 30, maxPwm: 100,
  onUpdatePoint: vi.fn(), onRemovePoint: vi.fn(), onAddPoint: vi.fn(),
};

describe('FanCurveTableEditor', () => {
  it('shows Add Point when editable and under 10 points', () => {
    const onAddPoint = vi.fn();
    render(<FanCurveTableEditor {...base} onAddPoint={onAddPoint} />);
    fireEvent.click(screen.getByText('system:fanControl.curve.addPoint'));
    expect(onAddPoint).toHaveBeenCalled();
  });

  it('renders plain values (no inputs) when not editable', () => {
    render(<FanCurveTableEditor {...base} canEdit={false} />);
    expect(screen.queryByText('system:fanControl.curve.addPoint')).not.toBeInTheDocument();
    expect(screen.getByText('40°C')).toBeInTheDocument();
  });

  it('maps the sorted first row back to its original (unsorted) index', () => {
    const onUpdatePoint = vi.fn();
    // Input is NOT pre-sorted: originalIndex 1 is the coldest (temp 40 -> renders first)
    const unsorted: FanCurvePoint[] = [{ temp: 60, pwm: 80 }, { temp: 40, pwm: 40 }];
    render(<FanCurveTableEditor {...base} curvePoints={unsorted} onUpdatePoint={onUpdatePoint} />);
    const tempInputs = screen.getAllByRole('spinbutton');
    // First rendered row is temp 40 => originalIndex 1, so the remap must report index 1
    fireEvent.change(tempInputs[0], { target: { value: '42' } });
    expect(onUpdatePoint).toHaveBeenCalledWith(1, 'temp', 42);
  });
});
