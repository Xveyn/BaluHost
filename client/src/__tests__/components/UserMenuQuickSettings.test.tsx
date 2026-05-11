import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import * as twoFactorApi from '../../api/two-factor';
import UserMenuQuickSettings from '../../components/UserMenuQuickSettings';
import { refreshStatus } from '../../components/quickSettings/twoFactorStatusStore';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'userMenu.quickSettings.byteUnits.binaryShort': 'GiB',
        'userMenu.quickSettings.byteUnits.decimalShort': 'GB',
      };
      return map[key] ?? key;
    },
    i18n: {
      language: 'de',
      changeLanguage: vi.fn(),
    },
  }),
}));

vi.mock('../../i18n', () => ({
  availableLanguages: [
    { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
    { code: 'en', name: 'English', flag: '🇬🇧' },
  ],
}));

describe('UserMenuQuickSettings', () => {
  it('renders the language section', () => {
    refreshStatus();
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockImplementation(
      () => new Promise(() => {})
    );
    render(<UserMenuQuickSettings onOpenSetup={vi.fn()} />);
    expect(screen.getByText('Deutsch')).toBeInTheDocument();
    expect(screen.getByText('English')).toBeInTheDocument();
  });

  it('renders the byte-unit section', () => {
    refreshStatus();
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockImplementation(
      () => new Promise(() => {})
    );
    render(<UserMenuQuickSettings onOpenSetup={vi.fn()} />);
    expect(screen.getByText('GiB')).toBeInTheDocument();
    expect(screen.getByText('GB')).toBeInTheDocument();
  });

  it('does not render 2FA prompt section while status is loading', () => {
    refreshStatus();
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockImplementation(
      () => new Promise(() => {})
    );
    const { container } = render(<UserMenuQuickSettings onCloseDropdown={vi.fn()} />);
    // The 2FA section should not appear; only Language + ByteUnit sections
    // The container should have exactly 3 children: LanguageSection, divider, ByteUnitSection
    const sections = container.querySelectorAll('section');
    expect(sections.length).toBe(2);
  });

  it('clicking the 2FA setup prompt invokes onOpenSetup', async () => {
    refreshStatus();
    vi.spyOn(twoFactorApi, 'get2FAStatus').mockResolvedValue({
      enabled: false,
      enabled_at: null,
      backup_codes_remaining: 0,
    });
    const onOpenSetup = vi.fn();
    render(<UserMenuQuickSettings onOpenSetup={onOpenSetup} />);
    // Wait specifically for the 2FA prompt button to appear after the async status resolves.
    // Language (2) + ByteUnit (2) buttons are always present; the 5th button is the prompt.
    // We wait until 5 buttons exist rather than using findAllByRole which resolves on the
    // first 4 (Language + ByteUnit) that are already in the DOM.
    let promptButton!: HTMLElement;
    await waitFor(() => {
      const buttons = screen.getAllByRole('button');
      expect(buttons).toHaveLength(5);
      promptButton = buttons[buttons.length - 1];
    });
    fireEvent.click(promptButton);
    expect(onOpenSetup).toHaveBeenCalledOnce();
  });
});
