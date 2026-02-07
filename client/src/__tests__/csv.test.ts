import { describe, it, expect } from 'vitest';
import { rowsToCsv } from '../lib/csv';

describe('rowsToCsv', () => {
  it('converts rows to CSV with header', () => {
    const rows = [
      { id: 1, name: 'Alice', note: 'Hello' },
      { id: 2, name: 'Bob', note: 'He said "Hi"' },
    ];
    const csv = rowsToCsv(rows, ['id', 'name', 'note']);
    const lines = csv.split('\n');
    expect(lines[0]).toBe('id,name,note');
    expect(lines[1]).toContain('Alice');
    expect(lines[2]).toContain('"He said ""Hi"""');
  });

  it('returns empty string for empty rows', () => {
    expect(rowsToCsv([])).toBe('');
  });

  it('returns empty string for null/undefined rows', () => {
    expect(rowsToCsv(null as any)).toBe('');
    expect(rowsToCsv(undefined as any)).toBe('');
  });

  it('handles null and undefined values as empty strings', () => {
    const rows = [{ a: null, b: undefined, c: 'ok' }];
    const csv = rowsToCsv(rows, ['a', 'b', 'c']);
    const lines = csv.split('\n');
    expect(lines[1]).toBe(',,ok');
  });

  it('uses Object.keys as columns when columns argument is omitted', () => {
    const rows = [{ x: 1, y: 2 }];
    const csv = rowsToCsv(rows);
    expect(csv.split('\n')[0]).toBe('x,y');
  });

  it('escapes values containing newlines', () => {
    const rows = [{ text: 'line1\nline2' }];
    const csv = rowsToCsv(rows, ['text']);
    expect(csv).toContain('"line1\nline2"');
  });

  it('escapes values containing commas', () => {
    const rows = [{ text: 'a,b' }];
    const csv = rowsToCsv(rows, ['text']);
    expect(csv).toContain('"a,b"');
  });
});
