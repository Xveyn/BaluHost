import { describe, it, expect } from 'vitest';
import de from '../../i18n/locales/de/admin.json';
import en from '../../i18n/locales/en/admin.json';

// The react-i18next mock in component tests echoes keys, so a key missing
// from the JSON only shows up in a contract test against the file itself.
describe('admin locale — system permission items', () => {
  it.each([['de', de], ['en', en]])('%s hat label und desc fuer launchGames', (_lang, locale) => {
    const item = locale.users.systemPermissions.items.launchGames;
    expect(item.label.length).toBeGreaterThan(0);
    expect(item.desc.length).toBeGreaterThan(0);
  });
});
