import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CacheArraySelector } from '../../../../components/ssd-cache/file-cache/CacheArraySelector';

describe('CacheArraySelector', () => {
  it('renders one button per array', () => {
    render(<CacheArraySelector arrays={['md0', 'md1']} selectedArray="md0" onSelect={() => {}} />);
    expect(screen.getByText('md0')).toBeInTheDocument();
    expect(screen.getByText('md1')).toBeInTheDocument();
  });
  it('fires onSelect with the clicked array name', () => {
    const onSelect = vi.fn();
    render(<CacheArraySelector arrays={['md0', 'md1']} selectedArray="md0" onSelect={onSelect} />);
    fireEvent.click(screen.getByText('md1'));
    expect(onSelect).toHaveBeenCalledWith('md1');
  });
});
