import { describe, expect, it } from 'vitest';

import de from '../../i18n/locales/de/scheduler.json';
import en from '../../i18n/locales/en/scheduler.json';

/**
 * Der react-i18next-Mock erfindet Interpolation — ein fehlender
 * {{platzhalter}} in der Locale-Datei fällt in Komponententests nicht auf.
 * Deshalb hier ein Vertragstest gegen die JSON-Dateien selbst.
 */
const REQUIRED: Record<string, string[]> = {
  'configModal.reboot.warningNever': ['window', 'windowEnds', 'retryHours'],
  'configModal.reboot.warningDeferred': ['window', 'windowEnds'],
};

function at(source: Record<string, unknown>, path: string): string {
  return path.split('.').reduce<unknown>(
    (acc, part) => (acc as Record<string, unknown>)?.[part], source,
  ) as string;
}

describe('scheduler locales — reboot warnings', () => {
  for (const [key, placeholders] of Object.entries(REQUIRED)) {
    for (const [name, bundle] of Object.entries({ de, en })) {
      it(`${name}: ${key} carries ${placeholders.join(', ')}`, () => {
        const value = at(bundle as Record<string, unknown>, key);
        expect(typeof value).toBe('string');
        for (const placeholder of placeholders) {
          expect(value).toContain(`{{${placeholder}}}`);
        }
      });
    }
  }
});
