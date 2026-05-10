import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LanguageSection } from '../../../components/quickSettings/LanguageSection';

let currentLanguage = 'de';
const changeLanguage = vi.fn((code: string) => {
  currentLanguage = code;
  return Promise.resolve();
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      get language() { return currentLanguage; },
      changeLanguage,
    },
  }),
}));

vi.mock('../../../i18n', () => ({
  availableLanguages: [
    { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
    { code: 'en', name: 'English', flag: '🇬🇧' },
  ],
}));

describe('LanguageSection', () => {
  beforeEach(() => {
    currentLanguage = 'de';
    changeLanguage.mockClear();
  });

  it('renders both available languages', () => {
    render(<LanguageSection />);
    expect(screen.getByText('Deutsch')).toBeInTheDocument();
    expect(screen.getByText('English')).toBeInTheDocument();
  });

  it('calls i18n.changeLanguage with the clicked language code', () => {
    render(<LanguageSection />);
    fireEvent.click(screen.getByText('English').closest('button')!);
    expect(changeLanguage).toHaveBeenCalledWith('en');
  });

  it('marks the active language with aria-pressed=true', () => {
    render(<LanguageSection />);
    const deBtn = screen.getByText('Deutsch').closest('button')!;
    const enBtn = screen.getByText('English').closest('button')!;
    expect(deBtn).toHaveAttribute('aria-pressed', 'true');
    expect(enBtn).toHaveAttribute('aria-pressed', 'false');
  });
});
