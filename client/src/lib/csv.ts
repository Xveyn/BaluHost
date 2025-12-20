export function rowsToCsv(rows: Array<Record<string, any>>, columns?: string[]): string {
  if (!rows || rows.length === 0) return '';
  const cols = columns && columns.length ? columns : Object.keys(rows[0]);
  const escape = (v: any) => {
    if (v === null || v === undefined) return '';
    const s = String(v);
    if (s.includes('"') || s.includes(',') || s.includes('\n')) {
      return '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
  };
  const hdr = cols.join(',');
  const lines = rows.map(r => cols.map(c => escape(r[c])).join(','));
  return [hdr, ...lines].join('\n');
}
