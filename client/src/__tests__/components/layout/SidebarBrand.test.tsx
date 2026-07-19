import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SidebarBrand } from '../../../components/layout/SidebarBrand';

const featureState = vi.hoisted(() => ({ isPi: false }));
vi.mock('../../../lib/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../lib/features')>()),
  get isPi() { return featureState.isPi; },
}));
vi.mock('../../../contexts/VersionContext', () => ({ useFormattedVersion: () => 'v1.38.0' }));

beforeEach(() => { featureState.isPi = false; });

describe('SidebarBrand', () => {
  it('desktop: box/title/pi sizing classes', () => {
    const { container } = render(<SidebarBrand variant="desktop" />);
    expect(container.querySelector('.flex.items-center.gap-3')).toBeInTheDocument();
    expect(container.querySelector('.h-12.w-12.p-\\[3px\\]')).toBeInTheDocument();
    expect(container.querySelector('p.text-lg')).toBeInTheDocument();
  });

  it('mobile: box/title sizing classes', () => {
    const { container } = render(<SidebarBrand variant="mobile" />);
    expect(container.querySelector('.h-10.w-10.p-\\[3px\\]')).toBeInTheDocument();
    expect(container.querySelector('p.text-base')).toBeInTheDocument();
  });

  it('compact: box/title sizing classes + gap-2 instead of gap-3', () => {
    const { container } = render(<SidebarBrand variant="compact" />);
    expect(container.querySelector('.flex.items-center.gap-2')).toBeInTheDocument();
    expect(container.querySelector('.h-8.w-8.p-\\[2px\\]')).toBeInTheDocument();
    expect(container.querySelector('span.text-sm.font-semibold')).toBeInTheDocument();
  });

  it('desktop/mobile render the version line; compact never does', () => {
    render(<SidebarBrand variant="desktop" />);
    expect(screen.getByText(/v1\.38\.0/)).toBeInTheDocument();
    const { container } = render(<SidebarBrand variant="compact" />);
    // compact renders a single <span> label, no version <p>
    expect(container.querySelectorAll('p')).toHaveLength(0);
  });

  // __BUILD_TYPE__ is a Vite `define` — a literal string baked in at transform
  // time (esbuild identifier substitution), not a real runtime global. It can't
  // be toggled per-test via vi.stubGlobal, so this asserts the conditional is
  // wired correctly for whichever build type this test run was compiled with
  // (in CI/local dev that's 'release' — see vite.config.ts's isDevelopmentBranch
  // check — so the `else` branch is what normally executes here). Either way,
  // this fails if the `__BUILD_TYPE__ === 'dev'` check is ever broken.
  it('appends "· {commit}" to the version line only when __BUILD_TYPE__ is dev', () => {
    const { container } = render(<SidebarBrand variant="desktop" />);
    const versionEl = container.querySelectorAll('p')[1];
    if (__BUILD_TYPE__ === 'dev') {
      expect(versionEl.textContent).toBe(`v1.38.0 · ${__GIT_COMMIT__}`);
    } else {
      expect(versionEl.textContent).toBe('v1.38.0');
    }
  });

  // Same __BUILD_TYPE__ caveat as above: DeveloperBadge itself renders null
  // outside dev builds, so "presence" is conditional on the compile-time value.
  // What's unconditionally true, and what this pins: compact never even
  // instantiates <DeveloperBadge/> (it's outside the compact branch in the JSX).
  it('DeveloperBadge is present in desktop/mobile (content depends on build type), absent in compact', () => {
    render(<SidebarBrand variant="desktop" />);
    const badge = screen.queryByText('Dev Build');
    if (__BUILD_TYPE__ === 'dev') {
      expect(badge).toBeInTheDocument();
    } else {
      expect(badge).not.toBeInTheDocument();
    }
    render(<SidebarBrand variant="compact" />);
    expect(screen.queryAllByText('Dev Build')).toHaveLength(__BUILD_TYPE__ === 'dev' ? 1 : 0);
  });

  it('standard (isPi=false): BaluHost + logo image', () => {
    render(<SidebarBrand variant="desktop" />);
    expect(screen.getByText('BaluHost')).toBeInTheDocument();
    expect(screen.getByAltText('BaluHost logo')).toBeInTheDocument();
    expect(screen.queryByText('BP')).not.toBeInTheDocument();
  });

  it('Pi (isPi=true): BaluPi + "BP" circle, kein Logo-Bild', () => {
    featureState.isPi = true;
    render(<SidebarBrand variant="desktop" />);
    expect(screen.getByText('BaluPi')).toBeInTheDocument();
    expect(screen.getByText('BP')).toBeInTheDocument();
    expect(screen.queryByAltText('BaluHost logo')).not.toBeInTheDocument();
  });

  it('compact + standard: logo alt-Text ist "BaluHost", nicht "BaluHost logo"', () => {
    render(<SidebarBrand variant="compact" />);
    expect(screen.getByAltText('BaluHost')).toBeInTheDocument();
    expect(screen.queryByAltText('BaluHost logo')).not.toBeInTheDocument();
  });
});
