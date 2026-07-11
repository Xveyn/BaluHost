import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { SharesTabBar } from '../../../components/shares/SharesTabBar';

describe('SharesTabBar', () => {
  it('renders a button per tab and reports clicks', () => {
    const onChange = vi.fn();
    render(<SharesTabBar activeTab="shares" onChange={onChange} />);
    // labels appear twice (full + short label); target the buttons by role
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(3);
    fireEvent.click(buttons[2]);
    expect(onChange).toHaveBeenCalledWith('cloud-exports');
  });
});
