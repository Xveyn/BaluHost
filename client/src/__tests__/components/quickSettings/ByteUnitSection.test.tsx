import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { setByteUnitMode } from '../../../lib/byteUnits';
import { ByteUnitSection } from '../../../components/quickSettings/ByteUnitSection';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'userMenu.quickSettings.byteUnits.title': 'Units',
        'userMenu.quickSettings.byteUnits.binaryShort': 'GiB',
        'userMenu.quickSettings.byteUnits.decimalShort': 'GB',
        'userMenu.quickSettings.byteUnits.binaryHint': 'binary',
        'userMenu.quickSettings.byteUnits.decimalHint': 'decimal',
      };
      return map[key] ?? key;
    },
  }),
}));

beforeEach(() => {
  act(() => {
    setByteUnitMode('binary');
  });
});

describe('ByteUnitSection', () => {
  it('renders both modes', () => {
    render(<ByteUnitSection />);
    expect(screen.getByText('GiB')).toBeInTheDocument();
    expect(screen.getByText('GB')).toBeInTheDocument();
  });

  it('marks binary as active by default', () => {
    render(<ByteUnitSection />);
    const binaryBtn = screen.getByText('GiB').closest('button')!;
    const decimalBtn = screen.getByText('GB').closest('button')!;
    expect(binaryBtn).toHaveAttribute('aria-pressed', 'true');
    expect(decimalBtn).toHaveAttribute('aria-pressed', 'false');
  });

  it('switches to decimal on click and updates the active state', () => {
    render(<ByteUnitSection />);
    fireEvent.click(screen.getByText('GB').closest('button')!);
    const binaryBtn = screen.getByText('GiB').closest('button')!;
    const decimalBtn = screen.getByText('GB').closest('button')!;
    expect(binaryBtn).toHaveAttribute('aria-pressed', 'false');
    expect(decimalBtn).toHaveAttribute('aria-pressed', 'true');
  });
});
