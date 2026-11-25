import { describe, it, expect } from 'vitest';
import de from '../../i18n/locales/de/localTls.json';
import en from '../../i18n/locales/en/localTls.json';

function flatten(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object'
      ? flatten(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  );
}

describe('localTls locale contract', () => {
  it('de und en haben dieselben Schluessel', () => {
    expect(flatten(de).sort()).toEqual(flatten(en).sort());
  });
  it('Token-Label des Backend-Adapters existiert', () => {
    expect(de.providers.duckdns.token.length).toBeGreaterThan(0);
    expect(en.providers.duckdns.token.length).toBeGreaterThan(0);
  });
  it('Pluralformen und expired in beiden Sprachen', () => {
    for (const l of [de, en]) {
      expect(l.cert.daysLeft_one).toContain('{{count}}');
      expect(l.cert.daysLeft_other).toContain('{{count}}');
      expect(l.cert.expired.length).toBeGreaterThan(0);
    }
  });
});
