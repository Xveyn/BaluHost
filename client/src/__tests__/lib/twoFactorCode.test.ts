import { describe, it, expect } from 'vitest';
import { sanitizeTwoFactorCode, isTwoFactorCodeComplete } from '../../lib/twoFactorCode';

describe('sanitizeTwoFactorCode', () => {
  it('strips non-digits in TOTP mode (unchanged legacy behaviour)', () => {
    expect(sanitizeTwoFactorCode('12ab34', false)).toBe('1234');
    expect(sanitizeTwoFactorCode('000000', false)).toBe('000000');
  });

  it('preserves hex chars and uppercases them in backup mode', () => {
    // Backup codes are secrets.token_hex(4).upper() -> 8 uppercase hex chars.
    // The old TOTP-only filter stripped the A-F letters, making backup codes
    // impossible to enter. Backup mode must keep them.
    expect(sanitizeTwoFactorCode('a3f9c2d1', true)).toBe('A3F9C2D1');
  });

  it('drops non-hex letters in backup mode', () => {
    expect(sanitizeTwoFactorCode('A3G9Z2D1', true)).toBe('A392D1');
  });

  it('caps at 8 chars in both modes', () => {
    expect(sanitizeTwoFactorCode('123456789', false)).toBe('12345678');
    expect(sanitizeTwoFactorCode('A3F9C2D1FF', true)).toBe('A3F9C2D1');
  });
});

describe('isTwoFactorCodeComplete', () => {
  it('TOTP needs at least 6 digits', () => {
    expect(isTwoFactorCodeComplete('12345', false)).toBe(false);
    expect(isTwoFactorCodeComplete('123456', false)).toBe(true);
    expect(isTwoFactorCodeComplete('12345678', false)).toBe(true);
  });

  it('backup code needs exactly 8 chars', () => {
    expect(isTwoFactorCodeComplete('A3F9C2D', true)).toBe(false);
    expect(isTwoFactorCodeComplete('A3F9C2D1', true)).toBe(true);
  });
});
