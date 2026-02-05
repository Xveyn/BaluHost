import {
  getAdminTables,
  getAdminTableSchema,
  getAdminTableRows,
  getAdminTableCategories,
  type AdminTableCategoriesResponse,
  type ColumnFilters,
} from '../lib/api'

export default function useAdminDb() {
  async function fetchTables(): Promise<string[]> {
    return getAdminTables()
  }

  async function fetchTableCategories(): Promise<AdminTableCategoriesResponse> {
    return getAdminTableCategories()
  }

  async function fetchSchema(table: string) {
    return getAdminTableSchema(table)
  }

  async function fetchRows(
    table: string,
    page = 1,
    page_size = 50,
    fields?: string[],
    q?: string,
    sort_by?: string,
    sort_order?: string,
    filters?: ColumnFilters
  ) {
    return getAdminTableRows(table, page, page_size, fields, q, sort_by, sort_order, filters)
  }

  return { fetchTables, fetchTableCategories, fetchSchema, fetchRows }
}
