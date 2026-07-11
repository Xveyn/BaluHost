import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { VclMessageBanners } from '../../../../components/vcl/vcl-settings/VclMessageBanners';

describe('VclMessageBanners', () => {
  it('renders only the error when only error is set', () => {
    render(<VclMessageBanners error="boom" successMessage={null} />);
    expect(screen.getByText('boom')).toBeInTheDocument();
  });
  it('renders only the success when only success is set', () => {
    render(<VclMessageBanners error={null} successMessage="done" />);
    expect(screen.getByText('done')).toBeInTheDocument();
  });
  it('renders nothing when both are null', () => {
    const { container } = render(<VclMessageBanners error={null} successMessage={null} />);
    expect(container.textContent).toBe('');
  });
});
