import { getAdminTables, getAdminTableSchema, getAdminTableRows } from '../lib/api'

export default function useAdminDb() {
  async function fetchTables(): Promise<string[]> {
    return getAdminTables()
  }

  async function fetchSchema(table: string) {
    return getAdminTableSchema(table)
  }

  async function fetchRows(table: string, page = 1, page_size = 50, fields?: string[], q?: string) {
    return getAdminTableRows(table, page, page_size, fields, q)
  }

  return { fetchTables, fetchSchema, fetchRows }
}
