import { describe, it, expect } from 'vitest';
import de from '../../i18n/locales/de/bluetooth.json';
import en from '../../i18n/locales/en/bluetooth.json';

function flatten(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object'
      ? flatten(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  );
}

describe('bluetooth locale contract', () => {
  it('de und en haben dieselben Schluessel', () => {
    expect(flatten(de).sort()).toEqual(flatten(en).sort());
  });

  // Der react-i18next-Mock der Komponententests erfindet die Interpolation
  // selbst; ein fehlender {{platzhalter}} faellt nur hier auf.
  it.each([
    ['battery', '{{percent}}'],
    ['removeConfirm', '{{name}}'],
    ['scanning', '{{seconds}}'],
  ])('%s traegt %s in beiden Sprachen', (key, placeholder) => {
    // `as unknown as`: ein direkter Cast auf Record<string, string> ist wegen
    // der verschachtelten Objekte TS2352 — und `tsc -b` prueft auch Tests.
    expect((de as unknown as Record<string, string>)[key]).toContain(placeholder);
    expect((en as unknown as Record<string, string>)[key]).toContain(placeholder);
  });

  it('dialog.title traegt {{name}} in beiden Sprachen', () => {
    expect(de.dialog.title).toContain('{{name}}');
    expect(en.dialog.title).toContain('{{name}}');
  });

  it('jeder Fehlerschluessel des Backends hat einen Text', () => {
    for (const key of ['auth_failed', 'unreachable', 'timeout', 'unknown']) {
      expect(de.dialog.error).toHaveProperty(key);
      expect(en.dialog.error).toHaveProperty(key);
    }
  });
});
