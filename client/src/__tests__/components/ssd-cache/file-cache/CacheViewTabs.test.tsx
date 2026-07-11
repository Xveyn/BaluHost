import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (_k: string, fb: string) => fb }) }));
import { CacheViewTabs } from '../../../../components/ssd-cache/file-cache/CacheViewTabs';

describe('CacheViewTabs', () => {
  it('renders both view tabs', () => {
    render(<CacheViewTabs tabView="cache" onSelect={() => {}} />);
    expect(screen.getByText('File Cache')).toBeInTheDocument();
    expect(screen.getByText('Data Migration')).toBeInTheDocument();
  });
  it('fires onSelect with the clicked view', () => {
    const onSelect = vi.fn();
    render(<CacheViewTabs tabView="cache" onSelect={onSelect} />);
    fireEvent.click(screen.getByText('Data Migration'));
    expect(onSelect).toHaveBeenCalledWith('migration');
  });
});
