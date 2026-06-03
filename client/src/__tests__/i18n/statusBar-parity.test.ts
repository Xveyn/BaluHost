import { describe, it, expect } from 'vitest';
import de from '../../i18n/locales/de/statusBar.json';
import en from '../../i18n/locales/en/statusBar.json';

function flatten(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object'
      ? flatten(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  );
}

describe('statusBar locale parity', () => {
  it('de and en have identical key sets', () => {
    expect(flatten(de as any).sort()).toEqual(flatten(en as any).sort());
  });

  it('has the new live label keys', () => {
    const keys = flatten(de as any);
    for (const k of ['pills.vpn.live', 'pills.pihole.live', 'pills.backup.live', 'pills.desktop.live']) {
      expect(keys).toContain(k);
    }
  });
});
