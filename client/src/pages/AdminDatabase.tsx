import { useState, useEffect } from 'react'
import useAdminDb from '../hooks/useAdminDb'
import AdminDataTable from '../components/AdminDataTable'
import { rowsToCsv } from '../lib/csv'

export default function AdminDatabase() {
  const [tables, setTables] = useState<string[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [page, setPage] = useState<number>(1)
  const [pageSize] = useState<number>(50)

  const { fetchTables, fetchSchema, fetchRows } = useAdminDb()
  const [schema, setSchema] = useState<any | null>(null)
  const [rows, setRows] = useState<any[]>([])
  const [ownerMap, setOwnerMap] = useState<Record<string,string>>({})
  const [ownerLoadInfo, setOwnerLoadInfo] = useState<{status: 'idle'|'loading'|'loaded'|'failed', page_size?: number, count?: number, keys?: string[], error?: string}>({status: 'idle'})
  const [total, setTotal] = useState<number | null>(null)
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  const totalPages = total ? Math.ceil((total ?? 0) / pageSize) : null
  useEffect(() => {
    let mounted = true
    setError(null)
    fetchTables()
      .then((t) => { if (mounted) setTables(t) })
      .catch((e) => { console.error('Failed to load admin tables', e); if (mounted) setError('Failed to load tables') })
    return () => { mounted = false }
  }, [])

  useEffect(() => {
    if (!selected) return
    let mounted = true
    setLoading(true)
    setError(null)
    Promise.all([fetchSchema(selected), fetchRows(selected, page, pageSize)])
      .then(([s, r]) => {
        if (!mounted) return
        setSchema(s)
        setRows(r.rows)
        setTotal(r.total ?? null)
      })
      .catch((e) => {
        console.error('Failed to load table data', e)
        if (mounted) setError('Fehler beim Laden der Tabellendaten')
      })
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [selected, page, pageSize])

  // Manual owner mapping loader to avoid accidental heavy DB queries.
  // Call `loadOwners()` (e.g. from UI) to populate `ownerMap` on demand.
  const loadOwners = async () => {
    if (!tables.includes('users')) {
      setOwnerLoadInfo({ status: 'failed', error: 'users table not available' })
      return
    }
    setOwnerLoadInfo({ status: 'loading' })
    let mounted = true
    try {
      const sizes = [2000, 1000, 500, 200, 100, 50]
      let successful = false
      for (const sz of sizes) {
        try {
          const res = await fetchRows('users', 1, sz)
          if (!mounted) return
          const map: Record<string,string> = {}
          for (const u of res.rows || []) {
            const id = u.id ?? u.ID ?? u.user_id ?? u.userId
            const name = u.username ?? u.user_name ?? u.name ?? u.display_name ?? u.displayName ?? ''
            if (id !== undefined) map[String(id)] = name
          }
          setOwnerMap(map)
          setOwnerLoadInfo({ status: 'loaded', page_size: sz, count: (res.rows || []).length, keys: Object.keys(map).slice(0,20) })
          successful = true
          break
        } catch (err: any) {
          const status = err?.response?.status
          if (status && status !== 422) {
            setOwnerLoadInfo({ status: 'failed', error: `HTTP ${status}` })
            break
          }
          setOwnerLoadInfo({ status: 'loading', page_size: sz })
        }
      }
      if (!successful) setOwnerLoadInfo({ status: 'failed', error: 'no successful response' })
    } catch (e) {
      setOwnerLoadInfo({ status: 'failed', error: String(e) })
    }
  }

  return (
    <div className="p-4 min-h-[70vh] w-full max-w-none">
      <h1 className="text-2xl font-semibold mb-4">Admin: Datenbank Ansicht</h1>

      <div className="flex gap-2">
        <main className="flex-1 flex flex-col">
          <div className="bg-gray-800 rounded-lg shadow px-3 py-6 flex flex-col min-h-[60vh]">
            <div className="flex items-start justify-between gap-4 mb-4">
              <div>
                <h2 className="text-xl font-semibold text-white">{selected ?? 'Datenbank Ansicht'}</h2>
                <p className="text-sm text-gray-400 mt-1">Wähle links eine Tabelle, um Schema und Zeilen anzuzeigen.</p>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setPage(Math.max(1, page - 1))}
                    className={`whitespace-nowrap rounded-lg border px-2 sm:px-3 py-1 sm:py-1.5 text-[10px] sm:text-xs transition touch-manipulation active:scale-95 ${page <= 1 ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500' : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-slate-600'}`}
                    disabled={page <= 1}
                  >Prev</button>
                  <div className="text-sm text-gray-400">Seite {page}{totalPages ? ` / ${totalPages}` : ''}</div>
                  <button
                    onClick={() => setPage(page + 1)}
                    className={`whitespace-nowrap rounded-lg border px-2 sm:px-3 py-1 sm:py-1.5 text-[10px] sm:text-xs transition touch-manipulation active:scale-95 ${totalPages !== null && page >= (totalPages ?? 1) ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500' : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-slate-600'}`}
                    disabled={totalPages !== null && page >= (totalPages ?? 1)}
                  >Next</button>
                </div>

                <div>
                  <button
                    disabled={!selected || rows.length === 0}
                    className={`inline-flex items-center gap-2 px-3 py-1 rounded text-sm transition ${selected && rows.length ? 'bg-sky-500 text-white' : 'bg-gray-700 text-gray-300 cursor-not-allowed'}`}
                    onClick={() => {
                      if (!selected || rows.length === 0) return
                      const cols = schema?.columns?.map((c: any) => c.name) ?? []
                      const csv = rowsToCsv(rows, cols)
                      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
                      const url = URL.createObjectURL(blob)
                      const a = document.createElement('a')
                      a.href = url
                      a.download = `${selected}.csv`
                      document.body.appendChild(a)
                      a.click()
                      a.remove()
                      URL.revokeObjectURL(url)
                    }}
                  >Export CSV</button>
                </div>
              </div>
            </div>

            {/* Table selector moved into the card header area */}
            <div className="mb-4">
              <div className="flex items-center gap-2">
                {tables.map((t) => (
                  <button
                    key={t}
                    onClick={() => { setSelected(t); setPage(1) }}
                    className={`px-3 py-1 rounded text-sm transition ${selected===t ? 'bg-gray-700 text-sky-200' : 'bg-gray-700/30 text-gray-300 hover:bg-gray-700/50'}`}>
                    {t}
                  </button>
                ))}
              </div>
            </div>

            {!selected && (
              <div className="text-gray-400">Wähle eine Tabelle aus der Liste.</div>
            )}

            {selected && (
              <>
                {error && <div className="bg-red-900/20 border border-red-500 text-red-400 px-4 py-3 rounded mb-4">{error}</div>}
                <div className="mb-4">
                  <h3 className="text-sm font-medium text-gray-300">Schema</h3>
                  <pre className="mt-2 text-xs text-gray-200 bg-gray-900/60 p-3 rounded overflow-auto" style={{ maxHeight: 220 }}>{schema ? JSON.stringify(schema, null, 2) : <span className="text-gray-500">Lädt...</span>}</pre>
                </div>

                <div className="mb-4">
                  <details className="text-sm text-gray-300">
                    <summary className="cursor-pointer">Owner mapping info</summary>
                    <div className="mt-2 text-xs text-gray-200 bg-gray-900/50 p-3 rounded">
                      <div>Status: <span className="font-medium">{ownerLoadInfo.status}</span></div>
                      {ownerLoadInfo.page_size && <div>Page size tried: {ownerLoadInfo.page_size}</div>}
                      {ownerLoadInfo.count !== undefined && <div>Loaded rows: {ownerLoadInfo.count}</div>}
                      {ownerLoadInfo.keys && ownerLoadInfo.keys.length > 0 && (
                        <div className="mt-2">Sample keys: {ownerLoadInfo.keys.join(', ')}</div>
                      )}
                      {ownerLoadInfo.error && <div className="mt-2 text-rose-400">Error: {ownerLoadInfo.error}</div>}
                      <div className="mt-3">
                        <button
                          onClick={() => loadOwners()}
                          className="inline-flex items-center gap-2 px-3 py-1 rounded bg-sky-500 text-white text-sm"
                        >Load owner names</button>
                        <span className="ml-3 text-xs text-gray-400">(manual, to avoid heavy DB load)</span>
                      </div>
                    </div>
                  </details>
                </div>


                <div className="flex-1 overflow-auto">
                  {loading ? (
                    <div className="flex items-center justify-center py-12 text-gray-400">Lade Zeilen...</div>
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
                    />
                  )}
                </div>
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
