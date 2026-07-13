import { Database, RefreshCw } from 'lucide-react'
import AdminDataTable from '../../AdminDataTable'
import ColumnFilterPanel from '../ColumnFilterPanel'
import TableSidebar from '../TableSidebar'
import RowDetailPanel from '../RowDetailPanel'
import BrowseToolbar from './BrowseToolbar'
import SchemaStrip from './SchemaStrip'
import OwnerMappingDetails from './OwnerMappingDetails'
import type { AdminTableSchemaField } from '../../../api/admin-db'
import type { useAdminDatabaseBrowse } from '../../../hooks/useAdminDatabaseBrowse'

type TableBrowserProps = ReturnType<typeof useAdminDatabaseBrowse>

/**
 * The full "browse" view: table sidebar + main panel (toolbar, schema strip,
 * owner mapping, data table) + row-detail panel. Extracted verbatim from
 * AdminDatabase's `renderBrowseContent`.
 */
export default function TableBrowser({
  tables,
  tableCategories,
  selected,
  handleTableSelect,
  globalSearch,
  setGlobalSearch,
  clearGlobalSearch,
  schema,
  showFilters,
  setShowFilters,
  activeFilterCount,
  filters,
  handleFiltersChange,
  pageSize,
  setPageSize,
  page,
  setPage,
  totalPages,
  rows,
  handleCsvExport,
  total,
  rangeStart,
  rangeEnd,
  error,
  ownerLoadInfo,
  loadOwners,
  loading,
  sortBy,
  sortOrder,
  handleSortChange,
  handleRowClick,
  ownerMap,
  selectedRow,
  setSelectedRow,
}: TableBrowserProps) {
  const columnCount = schema?.columns?.length ?? 0

  return (
    <div className="flex gap-4 min-h-[500px]">
      {/* Desktop Sidebar */}
      <TableSidebar
        tables={tables}
        categories={tableCategories}
        selected={selected}
        onSelect={handleTableSelect}
      />

      {/* Main Panel */}
      <div className="flex-1 min-w-0 card !p-0 overflow-hidden">
        {/* Toolbar */}
        <BrowseToolbar
          tables={tables}
          categories={tableCategories}
          selected={selected}
          onTableSelect={handleTableSelect}
          globalSearch={globalSearch}
          onGlobalSearchChange={setGlobalSearch}
          onClearGlobalSearch={clearGlobalSearch}
          columnCount={columnCount}
          showFilters={showFilters}
          onToggleFilters={() => setShowFilters(!showFilters)}
          activeFilterCount={activeFilterCount}
          pageSize={pageSize}
          onPageSizeChange={(size) => { setPageSize(size); setPage(1) }}
          page={page}
          totalPages={totalPages}
          onPageChange={setPage}
          rowCount={rows.length}
          onCsvExport={handleCsvExport}
          total={total}
          rangeStart={rangeStart}
          rangeEnd={rangeEnd}
        />

        {/* Card Body */}
        <div className="flex flex-1 min-h-0">
          <div className="flex-1 min-w-0">
            {!selected && (
              <div className="text-center py-16 px-4">
                <Database className="w-12 h-12 text-slate-700 mx-auto mb-4" />
                <p className="text-slate-400 text-sm font-medium">Select a table to view its data</p>
                <p className="text-slate-500 text-xs mt-1">{tables.length} tables available</p>
              </div>
            )}

            {selected && (
              <>
                {error && (
                  <div className="mx-4 sm:mx-5 mt-4 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
                    <p className="text-red-400 text-xs font-medium">{error}</p>
                  </div>
                )}

                {/* Column Filter Panel */}
                {showFilters && schema?.columns && (
                  <div className="mx-4 sm:mx-5 mt-4">
                    <ColumnFilterPanel
                      columns={schema.columns as AdminTableSchemaField[]}
                      filters={filters}
                      onFiltersChange={handleFiltersChange}
                    />
                  </div>
                )}

                {/* Schema Strip - always visible */}
                {schema?.columns && (
                  <SchemaStrip columns={schema.columns as AdminTableSchemaField[]} />
                )}

                {/* Owner Mapping - compact */}
                <OwnerMappingDetails ownerLoadInfo={ownerLoadInfo} onLoad={loadOwners} />

                {/* Data Table */}
                <div className="mt-3">
                  {loading ? (
                    <div className="flex items-center justify-center py-16 gap-3">
                      <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />
                      <span className="text-slate-400 text-sm">Loading rows...</span>
                    </div>
                  ) : (
                    <AdminDataTable
                      tableName={selected ?? undefined}
                      columns={schema?.columns ?? []}
                      rows={rows}
                      ownerMap={ownerMap}
                      page={page}
                      pageSize={pageSize}
                      total={total}
                      onPageChange={(p) => setPage(p)}
                      sortBy={sortBy}
                      sortOrder={sortOrder}
                      onSortChange={handleSortChange}
                      onRowClick={handleRowClick}
                    />
                  )}
                </div>
              </>
            )}
          </div>

          {/* Row Detail Panel (desktop) */}
          {selectedRow && schema?.columns && (
            <RowDetailPanel
              row={selectedRow}
              columns={schema.columns}
              onClose={() => setSelectedRow(null)}
              ownerMap={ownerMap}
            />
          )}
        </div>
      </div>
    </div>
  )
}
