import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '../lib/queryKeys'
import {
  getAdminTables,
  getAdminTableSchema,
  getAdminTableRows,
  getAdminTableCategories,
  type AdminTableSchemaResponse,
  type AdminTableRowsResponse,
  type ColumnFilters,
} from '../api/admin-db'

/**
 * Admin database inspector data hooks (TanStack Query, #299).
 *
 * The old default-export returned bare imperative fetch functions and the
 * AdminDatabase page drove everything through useEffect + useState. These two
 * queries replace that: table list/categories load once; schema+rows refetch
 * whenever the selected table or any browse parameter changes (key-driven).
 * The one-off owner-name loader stays imperative in the page (bespoke
 * page-size fallback) and calls `getAdminTableRows` directly.
 */

export interface AdminTableDataParams {
  page: number
  pageSize: number
  q?: string
  sortBy?: string
  sortOrder?: string
  filters?: ColumnFilters
}

export interface AdminTablesData {
  tables: string[]
  categories: Record<string, string[]>
}

export interface AdminTableData {
  schema: AdminTableSchemaResponse
  rows: AdminTableRowsResponse
}

/** Table list + category grouping — loaded once for the page. */
export function useAdminTables() {
  return useQuery<AdminTablesData>({
    queryKey: queryKeys.adminDb.tables(),
    queryFn: async () => {
      const [tables, categories] = await Promise.all([
        getAdminTables(),
        getAdminTableCategories(),
      ])
      return { tables, categories: categories.categories ?? {} }
    },
  })
}

/**
 * Schema + rows for the selected table. Disabled until a table is picked; the
 * key carries every browse parameter so any change refetches (and revisiting a
 * previous page/sort is served from cache).
 */
export function useAdminTableData(table: string | null, params: AdminTableDataParams) {
  return useQuery<AdminTableData>({
    queryKey: queryKeys.adminDb.tableData(table, { ...params }),
    queryFn: async () => {
      const t = table as string
      const [schema, rows] = await Promise.all([
        getAdminTableSchema(t),
        getAdminTableRows(
          t,
          params.page,
          params.pageSize,
          undefined,
          params.q,
          params.sortBy,
          params.sortOrder,
          params.filters,
        ),
      ])
      return { schema, rows }
    },
    enabled: table !== null,
  })
}
