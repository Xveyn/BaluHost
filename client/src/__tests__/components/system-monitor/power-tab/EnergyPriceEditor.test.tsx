import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../../../../lib/formatters', () => ({ formatNumber: (value: number, decimals: number) => value.toFixed(decimals) }));

import { EnergyPriceEditor } from '../../../../components/system-monitor/power-tab/EnergyPriceEditor';
import type { EnergyPriceConfig } from '../../../../api/energy';

const priceConfig: EnergyPriceConfig = {
  id: 1,
  cost_per_kwh: 0.4,
  currency: 'EUR',
  updated_at: '2026-01-01T00:00:00Z',
  updated_by_user_id: null,
};

describe('EnergyPriceEditor', () => {
  it('view mode: shows price text and clicking pencil button fires onEdit', () => {
    const onEdit = vi.fn();
    render(
      <EnergyPriceEditor
        priceConfig={priceConfig}
        editing={false}
        priceInput="0.40"
        saving={false}
        onEdit={onEdit}
        onInputChange={vi.fn()}
        onSave={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByText('0.40 EUR/kWh')).toBeTruthy();

    fireEvent.click(screen.getByRole('button'));
    expect(onEdit).toHaveBeenCalledTimes(1);
  });

  it('edit mode: input reflects priceInput, change fires onInputChange, save/cancel buttons fire callbacks', () => {
    const onInputChange = vi.fn();
    const onSave = vi.fn();
    const onCancel = vi.fn();
    render(
      <EnergyPriceEditor
        priceConfig={priceConfig}
        editing={true}
        priceInput="0.45"
        saving={false}
        onEdit={vi.fn()}
        onInputChange={onInputChange}
        onSave={onSave}
        onCancel={onCancel}
      />,
    );

    const input = screen.getByDisplayValue('0.45') as HTMLInputElement;
    expect(input).toBeTruthy();

    fireEvent.change(input, { target: { value: '0.55' } });
    expect(onInputChange).toHaveBeenCalledWith('0.55');

    fireEvent.click(screen.getByText('✓'));
    expect(onSave).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText('✕'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('edit mode: shows "..." on save button and disables inputs/buttons while saving', () => {
    render(
      <EnergyPriceEditor
        priceConfig={priceConfig}
        editing={true}
        priceInput="0.45"
        saving={true}
        onEdit={vi.fn()}
        onInputChange={vi.fn()}
        onSave={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByText('...')).toBeTruthy();
    const input = screen.getByDisplayValue('0.45') as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });
});
