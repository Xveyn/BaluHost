import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Toggle, ToggleRow, NumberInput } from '../../../../components/power/sleep-config/SleepFormControls';

describe('SleepFormControls', () => {
  it('Toggle flips its value on click', () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('ToggleRow renders its label and toggles', () => {
    const onChange = vi.fn();
    render(<ToggleRow label="Pause monitoring" checked onChange={onChange} />);
    expect(screen.getByText('Pause monitoring')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button'));
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it('NumberInput reports a numeric value', () => {
    const onChange = vi.fn();
    render(<NumberInput label="Idle timeout (min)" value={15} onChange={onChange} />);
    // label and input are siblings (no htmlFor/id) -> use getByText for the label
    expect(screen.getByText('Idle timeout (min)')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '20' } });
    expect(onChange).toHaveBeenCalledWith(20);
  });
});
