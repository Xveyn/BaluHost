import i18n from '../i18n'

/**
 * Format a database cell value for display.
 * Shared between AdminDataTable and RowDetailPanel.
 */
export function formatAdminValue(name: string, raw: any, t: (key: string) => string): string {
  if (raw === null || raw === undefined) return '-'
  const n = name.toLowerCase()

  // sizes / numeric IDs
  if (n.includes('size') || n.includes('bytes') || n === 'owner_id' || n.endsWith('_id')) {
    if (typeof raw === 'number') return new Intl.NumberFormat(i18n.language).format(raw)
    const num = Number(raw)
    return Number.isFinite(num) ? new Intl.NumberFormat(i18n.language).format(num) : String(raw)
  }

  // booleans
  if (n.startsWith('is_') || n === 'is_directory' || typeof raw === 'boolean') {
    return raw ? t('common.true') : t('common.false')
  }

  // dates
  if (n.includes('created') || n.includes('updated') || n.includes('date') || n.includes('at')) {
    const d = new Date(raw)
    if (!isNaN(d.getTime())) return d.toLocaleString()
  }

  return String(raw)
}
