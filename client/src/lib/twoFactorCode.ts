/**
 * Sanitisation + completeness helpers for the 2FA login code input.
 *
 * Two code kinds are entered through the same field on the login screen:
 *  - TOTP codes: 6-8 digits from the authenticator app.
 *  - Backup codes: 8 uppercase hex chars (backend: `secrets.token_hex(4).upper()`).
 *
 * The original input filter stripped every non-digit, so a backup code's A-F
 * letters were silently removed and a backup code could never be entered. These
 * helpers make the filter mode-aware.
 */

const BACKUP_CODE_LENGTH = 8;
const TOTP_MIN_LENGTH = 6;
const MAX_LENGTH = 8;

/** Filter raw keystrokes for the active mode. */
export function sanitizeTwoFactorCode(raw: string, backupMode: boolean): string {
  if (backupMode) {
    return raw.replace(/[^0-9a-fA-F]/g, '').toUpperCase().slice(0, MAX_LENGTH);
  }
  return raw.replace(/\D/g, '').slice(0, MAX_LENGTH);
}

/** Whether the entered code is long enough to allow submitting. */
export function isTwoFactorCodeComplete(code: string, backupMode: boolean): boolean {
  return backupMode ? code.length === BACKUP_CODE_LENGTH : code.length >= TOTP_MIN_LENGTH;
}
