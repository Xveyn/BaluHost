import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { DesktopSidebar } from '../../../components/layout/DesktopSidebar';
import type { LayoutNavItem } from '../../../components/layout/layoutNavConfig';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../../../contexts/VersionContext', () => ({ useFormattedVersion: () => 'v1.38.0' }));

const items: LayoutNavItem[] = [
  { path: '/', label: 'Dash', description: 'd', icon: <span /> },
];

function renderSidebar(isImpersonating: boolean) {
  return render(
    <MemoryRouter>
      <DesktopSidebar isImpersonating={isImpersonating} items={items} adminStartIndex={-1} />
    </MemoryRouter>,
  );
}

describe('DesktopSidebar', () => {
  // Regression coverage: DesktopSidebar has no isImpersonating-driven fallback —
  // dropping the prop entirely would still satisfy every other test in the
  // suite (Layout.test.tsx only asserts the offsets on <header>/<main>, never
  // on the desktop <aside>). These two tests pin the offset classes directly.
  it('normal: top-0 h-screen, kein Impersonation-Offset', () => {
    const { container } = renderSidebar(false);
    const aside = container.querySelector('aside')!;
    expect(aside.className).toContain('top-0 h-screen');
    expect(aside.className).not.toContain('top-10');
  });

  it('Impersonation: top-10 h-[calc(100vh-2.5rem)]', () => {
    const { container } = renderSidebar(true);
    const aside = container.querySelector('aside')!;
    expect(aside.className).toContain('top-10 h-[calc(100vh-2.5rem)]');
    expect(aside.className).not.toContain('top-0 h-screen');
  });
});
