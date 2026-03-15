import { describe, it, expect, vi } from 'vitest';
import { formatAdminValue } from '../../lib/adminDbFormatters';

// Mock i18n is already set up in setup.ts (language: 'de')

const t = (key: string) => {
  const translations: Record<string, string> = {
    'common.true': 'Ja',
    'common.false': 'Nein',
  };
  return translations[key] ?? key;
};

describe('formatAdminValue', () => {
  it('returns "-" for null/undefined', () => {
    expect(formatAdminValue('name', null, t)).toBe('-');
    expect(formatAdminValue('name', undefined, t)).toBe('-');
  });

  it('formats numeric size columns with locale', () => {
    const result = formatAdminValue('file_size', 1234567, t);
    // Intl.NumberFormat with 'de' should produce something with separators
    expect(result).toContain('1');
    expect(result.length).toBeGreaterThan(1);
  });

  it('formats numeric ID columns', () => {
    const result = formatAdminValue('owner_id', 42, t);
    expect(result).toBe('42');
  });

  it('formats string numbers in size columns', () => {
    const result = formatAdminValue('total_bytes', '9999', t);
    expect(result).toContain('9');
  });

  it('returns raw string if not a valid number in size column', () => {
    expect(formatAdminValue('size_note', 'unknown', t)).toBe('unknown');
  });

  it('formats booleans for is_ columns', () => {
    expect(formatAdminValue('is_directory', true, t)).toBe('Ja');
    expect(formatAdminValue('is_directory', false, t)).toBe('Nein');
    expect(formatAdminValue('is_active', true, t)).toBe('Ja');
  });

  it('formats boolean values regardless of column name', () => {
    expect(formatAdminValue('enabled', true, t)).toBe('Ja');
    expect(formatAdminValue('enabled', false, t)).toBe('Nein');
  });

  it('formats date columns', () => {
    const result = formatAdminValue('created_at', '2026-01-15T10:30:00Z', t);
    // Should produce a locale date string, not the raw ISO string
    expect(result).not.toBe('2026-01-15T10:30:00Z');
    expect(result.length).toBeGreaterThan(5);
  });

  it('returns raw string for invalid dates in date columns', () => {
    expect(formatAdminValue('updated_at', 'not-a-date', t)).toBe('not-a-date');
  });

  it('stringifies other values', () => {
    expect(formatAdminValue('username', 'admin', t)).toBe('admin');
    expect(formatAdminValue('count', 7, t)).toBe('7');
  });
});
