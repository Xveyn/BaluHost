import { describe, it, expect } from 'vitest';
import { formatMode } from '../../api/displayOutput';

const MODE_120 = { id: '57', name: '3840x2160@120', width: 3840, height: 2160, refresh_rate: 120 };
const MODE_11988 = {
  id: '58', name: '3840x2160@120', width: 3840, height: 2160,
  refresh_rate: 119.87999725341797,
};

describe('formatMode', () => {
  it('trennt das Paar, das denselben Namen traegt', () => {
    // Genau hier scheitert die Adressierung ueber den Namen: beide heissen
    // "3840x2160@120". Zwei Nachkommastellen machen sie unterscheidbar.
    expect(formatMode(MODE_120, 'de')).not.toBe(formatMode(MODE_11988, 'de'));
  });

  it('rundet auf zwei Nachkommastellen', () => {
    expect(formatMode(MODE_11988, 'en')).toContain('119.88');
    expect(formatMode(MODE_120, 'en')).toContain('120.00');
  });

  it('nutzt das Dezimaltrennzeichen der Sprache', () => {
    expect(formatMode(MODE_11988, 'de')).toContain('119,88');
  });

  it('nennt Aufloesung und Einheit', () => {
    expect(formatMode(MODE_120, 'en')).toBe('3840 × 2160 @ 120.00 Hz');
  });
});
