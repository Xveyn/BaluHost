import { describe, it, expect, beforeAll, vi } from 'vitest';

// The global test setup (src/__tests__/setup.ts) mocks the i18n module with a
// bare stub ({ default: { language: 'de' } }) so other component tests don't pull
// in the full i18next runtime. This regression test, by contrast, NEEDS the real
// configured instance to prove namespace resolution, so un-mock it for this file.
vi.unmock('../../../i18n');

const { default: i18n } = await import('../../../i18n');

beforeAll(async () => {
  await i18n.changeLanguage('en');
});

describe('statusBar pill name i18n resolution', () => {
  it('resolves the ns-relative key to the real English translation', () => {
    // This is the form the component must pass after stripping the backend "statusBar." prefix.
    expect(i18n.t('pills.power.name', { ns: 'statusBar' })).toBe('Power Profile');
    expect(i18n.t('pills.alwaysAwake.name', { ns: 'statusBar' })).toBe('Always Awake / Core Hours');
  });

  it('does NOT resolve the raw backend key (regression guard for the namespace bug)', () => {
    // The dotted ns-prefixed key must NOT accidentally resolve; if it ever does,
    // the strip-prefix fix may be unnecessary — but today it returns the raw key.
    expect(i18n.t('statusBar.pills.power.name', { ns: 'statusBar' })).toBe('statusBar.pills.power.name');
  });

  it('resolves German too', async () => {
    await i18n.changeLanguage('de');
    expect(i18n.t('pills.power.name', { ns: 'statusBar' })).toBe('Energieprofil');
    await i18n.changeLanguage('en');
  });
});
