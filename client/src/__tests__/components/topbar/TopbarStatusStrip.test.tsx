import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TopbarStatusStrip } from '../../../components/topbar/TopbarStatusStrip';
import type { StatusBarStateResponse } from '../../../api/statusBar';

vi.mock('../../../hooks/useStatusBarState', () => ({
  useStatusBarState: () => ({ state: null, stale: false }),
}));

function preview(pills: any[]): StatusBarStateResponse {
  return { pills, show_bottom_upload: true };
}

describe('TopbarStatusStrip', () => {
  it('renders nothing when there are no pills', () => {
    const { container } = render(
      <MemoryRouter><TopbarStatusStrip previewState={preview([])} /></MemoryRouter>,
    );
    expect(container.querySelectorAll('a')).toHaveLength(0);
  });

  it('renders pills in payload order', () => {
    const pills = [
      { id: 'pihole', kind: 'state', tone: 'success', label: 'Pi-hole', value: 'on', href: '/pihole', icon: 'Shield', extra: null },
      { id: 'power', kind: 'state', tone: 'info', label: 'Power', value: null, href: '/x', icon: 'Zap', extra: null },
    ];
    render(<MemoryRouter><TopbarStatusStrip previewState={preview(pills)} /></MemoryRouter>);
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveTextContent('Pi-hole');
    expect(links[1]).toHaveTextContent('Power');
  });

  it('renders a divider between pills but not before the first', () => {
    const twoPills = [
      { id: 'pihole', kind: 'state', tone: 'success', label: 'Pi-hole', value: 'on', href: '/pihole', icon: 'Shield', extra: null },
      { id: 'power', kind: 'state', tone: 'info', label: 'Power', value: null, href: '/x', icon: 'Zap', extra: null },
    ];
    const { container } = render(
      <MemoryRouter><TopbarStatusStrip previewState={preview(twoPills)} /></MemoryRouter>,
    );
    // one divider for two pills (n-1)
    expect(container.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(1);
  });

  it('renders no divider for a single pill', () => {
    const onePill = [
      { id: 'power', kind: 'state', tone: 'info', label: 'Power', value: null, href: '/x', icon: 'Zap', extra: null },
    ];
    const { container } = render(
      <MemoryRouter><TopbarStatusStrip previewState={preview(onePill)} /></MemoryRouter>,
    );
    expect(container.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(0);
  });
});
