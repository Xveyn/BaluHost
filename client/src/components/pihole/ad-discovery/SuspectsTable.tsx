import { useState, useEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Ban, XCircle, CheckCircle, Plus } from 'lucide-react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import {
  getSuspects,
  updateSuspectStatus,
  blockSuspect,
  addManualSuspect,
  bulkAction,
  type SuspectEntry,
} from '../../../api/adDiscovery';
import BlockDialog from './BlockDialog';
import { useSortableTable } from '../../../hooks/useSortableTable';
import { SortableHeader } from '../../ui/SortableHeader';

function scoreColor(score: number): string {
  if (score >= 0.8) return 'text-red-400';
  if (score >= 0.5) return 'text-orange-400';
  return 'text-yellow-400';
}

function scoreBg(score: number): string {
  if (score >= 0.8) return 'bg-red-500/10';
  if (score >= 0.5) return 'bg-orange-500/10';
  return 'bg-yellow-500/10';
}

export default function SuspectsTable() {
  const { t } = useTranslation('pihole');
  const [suspects, setSuspects] = useState<SuspectEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [sourceFilter, setSourceFilter] = useState<string>('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [blockingDomain, setBlockingDomain] = useState<string | null>(null);
  const [manualDomain, setManualDomain] = useState('');
  const [showManualAdd, setShowManualAdd] = useState(false);
  const { sortedData: sortedSuspects, sortKey, sortDirection, toggleSort } = useSortableTable(suspects, {
    defaultSort: { key: 'heuristic_score', direction: 'desc' },
  });

  const statusLabel = (status: string) => {
    switch (status) {
      case 'new':
        return t('adDiscovery.suspects.filters.statusNew');
      case 'confirmed':
        return t('adDiscovery.suspects.filters.statusConfirmed');
      case 'dismissed':
        return t('adDiscovery.suspects.filters.statusDismissed');
      case 'blocked':
        return t('adDiscovery.suspects.filters.statusBlocked');
      default:
        return status;
    }
  };

  const sourceLabel = (source: string) => {
    switch (source) {
      case 'heuristic':
        return t('adDiscovery.suspects.filters.sourceHeuristic');
      case 'community':
        return t('adDiscovery.suspects.filters.sourceCommunity');
      case 'both':
        return t('adDiscovery.suspects.filters.sourceBoth');
      case 'manual':
        return t('adDiscovery.suspects.filters.sourceManual');
      default:
        return source;
    }
  };

  const statusBadge = (status: string) => {
    const colors: Record<string, string> = {
      new: 'bg-blue-500/20 text-blue-300',
      confirmed: 'bg-orange-500/20 text-orange-300',
      dismissed: 'bg-slate-500/20 text-slate-400',
      blocked: 'bg-red-500/20 text-red-300',
    };
    return (
      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] || 'bg-slate-600 text-slate-300'}`}>
        {statusLabel(status)}
      </span>
    );
  };

  const sourceBadge = (source: string) => {
    const colors: Record<string, string> = {
      heuristic: 'bg-purple-500/20 text-purple-300',
      community: 'bg-green-500/20 text-green-300',
      both: 'bg-cyan-500/20 text-cyan-300',
      manual: 'bg-slate-500/20 text-slate-400',
    };
    return (
      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colors[source] || 'bg-slate-600 text-slate-300'}`}>
        {sourceLabel(source)}
      </span>
    );
  };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (statusFilter) params.status = statusFilter;
      if (sourceFilter) params.source = sourceFilter;
      const result = await getSuspects(params);
      setSuspects(result.suspects);
      setTotal(result.total);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || t('adDiscovery.suspects.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, statusFilter, sourceFilter, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleStatusChange = async (domain: string, status: string) => {
    try {
      await updateSuspectStatus(domain, status);
      toast.success(t('adDiscovery.suspects.markedAs', { domain, status: statusLabel(status) }));
      fetchData();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || t('adDiscovery.suspects.updateStatusFailed'));
    }
  };

  const handleBlock = async (domain: string, target: string, listId?: number) => {
    try {
      await blockSuspect(domain, target, listId);
      toast.success(t('adDiscovery.suspects.blockedToast', { domain }));
      setBlockingDomain(null);
      fetchData();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || t('adDiscovery.suspects.blockFailed'));
    }
  };

  const handleManualAdd = async () => {
    const d = manualDomain.trim();
    if (!d) return;
    try {
      await addManualSuspect(d);
      toast.success(t('adDiscovery.suspects.addedSuspect', { domain: d }));
      setManualDomain('');
      setShowManualAdd(false);
      fetchData();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || t('adDiscovery.suspects.addManualFailed'));
    }
  };

  const handleBulkAction = async (action: string) => {
    if (selected.size === 0) return;
    try {
      await bulkAction(Array.from(selected), action);
      toast.success(t('adDiscovery.suspects.bulkApplied', { action, count: selected.size }));
      setSelected(new Set());
      fetchData();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || t('adDiscovery.suspects.bulkFailed'));
    }
  };

  const toggleSelect = (domain: string) => {
    const next = new Set(selected);
    if (next.has(domain)) next.delete(domain);
    else next.add(domain);
    setSelected(next);
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-4">
      {/* Filters & Actions */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-sm text-white"
        >
          <option value="">{t('adDiscovery.suspects.filters.allStatuses')}</option>
          <option value="new">{t('adDiscovery.suspects.filters.statusNew')}</option>
          <option value="confirmed">{t('adDiscovery.suspects.filters.statusConfirmed')}</option>
          <option value="dismissed">{t('adDiscovery.suspects.filters.statusDismissed')}</option>
          <option value="blocked">{t('adDiscovery.suspects.filters.statusBlocked')}</option>
        </select>
        <select
          value={sourceFilter}
          onChange={(e) => {
            setSourceFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-sm text-white"
        >
          <option value="">{t('adDiscovery.suspects.filters.allSources')}</option>
          <option value="heuristic">{t('adDiscovery.suspects.filters.sourceHeuristic')}</option>
          <option value="community">{t('adDiscovery.suspects.filters.sourceCommunity')}</option>
          <option value="both">{t('adDiscovery.suspects.filters.sourceBoth')}</option>
          <option value="manual">{t('adDiscovery.suspects.filters.sourceManual')}</option>
        </select>
        <div className="flex-1" />
        {selected.size > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">{t('adDiscovery.suspects.selected', { count: selected.size })}</span>
            <button
              onClick={() => handleBulkAction('dismiss')}
              className="rounded bg-slate-600 px-2 py-1 text-xs text-white hover:bg-slate-500"
            >
              {t('adDiscovery.suspects.dismiss')}
            </button>
            <button
              onClick={() => handleBulkAction('block')}
              className="rounded bg-red-600 px-2 py-1 text-xs text-white hover:bg-red-500"
            >
              {t('adDiscovery.suspects.blockAll')}
            </button>
          </div>
        )}
        <button
          onClick={() => setShowManualAdd(!showManualAdd)}
          className="flex items-center gap-1.5 rounded-md bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-600"
        >
          <Plus className="h-4 w-4" /> {t('adDiscovery.suspects.addManual')}
        </button>
      </div>

      {/* Manual Add */}
      {showManualAdd && (
        <div className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/60 p-3">
          <input
            value={manualDomain}
            onChange={(e) => setManualDomain(e.target.value)}
            placeholder={t('adDiscovery.suspects.addPlaceholder')}
            onKeyDown={(e) => e.key === 'Enter' && handleManualAdd()}
            className="flex-1 rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-sm text-white placeholder-slate-500"
          />
          <button
            onClick={handleManualAdd}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-500"
          >
            {t('adDiscovery.suspects.add')}
          </button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-700/50">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-700 bg-slate-800/60">
            <tr>
              <th className="w-8 px-3 py-3">
                <input
                  type="checkbox"
                  className="rounded border-slate-600"
                  onChange={(e) => setSelected(e.target.checked ? new Set(suspects.map((s) => s.domain)) : new Set())}
                />
              </th>
              <SortableHeader label={t('adDiscovery.suspects.columns.domain')} sortKey="domain" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-3 py-3 text-slate-400 font-medium" />
              <SortableHeader label={t('adDiscovery.suspects.columns.score')} sortKey="heuristic_score" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-3 py-3 text-slate-400 font-medium" />
              <SortableHeader label={t('adDiscovery.suspects.columns.source')} sortKey="source" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-3 py-3 text-slate-400 font-medium" />
              <SortableHeader label={t('adDiscovery.suspects.columns.queries')} sortKey="query_count" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-3 py-3 text-slate-400 font-medium" />
              <SortableHeader label={t('adDiscovery.suspects.columns.community')} sortKey="community_hits" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-3 py-3 text-slate-400 font-medium" />
              <SortableHeader label={t('adDiscovery.suspects.columns.status')} sortKey="status" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-3 py-3 text-slate-400 font-medium" />
              <th className="px-3 py-3 text-slate-400 font-medium">{t('adDiscovery.suspects.columns.actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {loading ? (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-slate-500">
                  {t('adDiscovery.suspects.loading')}
                </td>
              </tr>
            ) : suspects.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-slate-500">
                  {t('adDiscovery.suspects.noResults')}
                </td>
              </tr>
            ) : (
              sortedSuspects.map((s) => (
                <tr key={s.id} className="hover:bg-slate-800/40">
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selected.has(s.domain)}
                      onChange={() => toggleSelect(s.domain)}
                      className="rounded border-slate-600"
                    />
                  </td>
                  <td className="px-3 py-2 text-white font-mono text-xs">{s.domain}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${scoreColor(s.heuristic_score)} ${scoreBg(s.heuristic_score)}`}>
                      {s.heuristic_score.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-3 py-2">{sourceBadge(s.source)}</td>
                  <td className="px-3 py-2 text-slate-300">{s.query_count.toLocaleString()}</td>
                  <td className="px-3 py-2 text-slate-300">
                    {s.community_hits > 0
                      ? t('adDiscovery.suspects.lists', { count: s.community_hits })
                      : '—'}
                  </td>
                  <td className="px-3 py-2">{statusBadge(s.status)}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1">
                      {s.status !== 'blocked' && (
                        <button
                          onClick={() => setBlockingDomain(s.domain)}
                          title={t('adDiscovery.suspects.blockDialog.block')}
                          className="rounded p-1 text-red-400 hover:bg-red-500/10"
                        >
                          <Ban className="h-4 w-4" />
                        </button>
                      )}
                      {s.status !== 'dismissed' && s.status !== 'blocked' && (
                        <button
                          onClick={() => handleStatusChange(s.domain, 'dismissed')}
                          title={t('adDiscovery.suspects.dismiss')}
                          className="rounded p-1 text-slate-400 hover:bg-slate-500/10"
                        >
                          <XCircle className="h-4 w-4" />
                        </button>
                      )}
                      {s.status === 'new' && (
                        <button
                          onClick={() => handleStatusChange(s.domain, 'confirmed')}
                          title={t('adDiscovery.suspects.filters.statusConfirmed')}
                          className="rounded p-1 text-green-400 hover:bg-green-500/10"
                        >
                          <CheckCircle className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-400">{t('adDiscovery.suspects.total', { count: total })}</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-md p-1.5 text-slate-400 hover:text-white disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-sm text-slate-300">{t('adDiscovery.suspects.page', { page, total: totalPages })}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="rounded-md p-1.5 text-slate-400 hover:text-white disabled:opacity-30"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Block Dialog */}
      {blockingDomain && (
        <BlockDialog
          domain={blockingDomain}
          onConfirm={(t, l) => handleBlock(blockingDomain, t, l)}
          onCancel={() => setBlockingDomain(null)}
        />
      )}
    </div>
  );
}
