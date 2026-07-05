import { useState, useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Database, RefreshCw, Power, PowerOff } from 'lucide-react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import {
  getCollectorStatus,
  updateCollectorConfig,
  type QueryCollectorStatus as CollectorStatus,
} from '../../api/pihole';
import { queryKeys } from '../../lib/queryKeys';
import { getApiErrorMessage } from '../../lib/errorHandling';

export default function QueryCollectorStatus() {
  const { t } = useTranslation('pihole');
  const queryClient = useQueryClient();

  // Query-backed (#299): 15s status poll. Errors are swallowed (collector may
  // not be initialized yet) → status stays null and the component renders null.
  const { data: status = null, isLoading: loading } = useQuery({
    queryKey: queryKeys.pihole.collectorStatus(),
    queryFn: getCollectorStatus,
    refetchInterval: 15000,
  });

  const [pollInterval, setPollInterval] = useState(30);
  const [retentionDays, setRetentionDays] = useState(30);

  // Seed the editable form from the config ONCE on first load (dirty-guard): the
  // old code re-synced these fields on every 15s poll, clobbering in-progress
  // edits. A save re-seeds via the mutation below.
  const seededRef = useRef(false);
  useEffect(() => {
    if (status && !seededRef.current) {
      seededRef.current = true;
      setPollInterval(status.poll_interval_seconds);
      setRetentionDays(status.retention_days);
    }
  }, [status]);

  const applyConfig = (data: CollectorStatus) => {
    queryClient.setQueryData(queryKeys.pihole.collectorStatus(), data);
  };

  const toggleMutation = useMutation({
    mutationFn: () => updateCollectorConfig({ is_enabled: !status!.is_enabled }),
    onSuccess: (data) => {
      applyConfig(data);
      toast.success(data.is_enabled ? t('collector.enabledToast') : t('collector.disabledToast'));
    },
    onError: (err) => toast.error(getApiErrorMessage(err, t('collector.updateFailed'))),
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      updateCollectorConfig({ poll_interval_seconds: pollInterval, retention_days: retentionDays }),
    onSuccess: (data) => {
      applyConfig(data);
      setPollInterval(data.poll_interval_seconds);
      setRetentionDays(data.retention_days);
      toast.success(t('collector.savedToast'));
    },
    onError: (err) => toast.error(getApiErrorMessage(err, t('collector.saveFailed'))),
  });

  const saving = toggleMutation.isPending || saveMutation.isPending;
  const handleToggle = () => {
    if (!status) return;
    toggleMutation.mutate();
  };
  const handleSave = () => {
    saveMutation.mutate();
  };

  if (loading) {
    return (
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
        <div className="h-32 animate-pulse rounded bg-slate-700" />
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <Database className="h-5 w-5 text-slate-400" />
          <h4 className="text-sm font-medium text-slate-200">{t('collector.title')}</h4>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
              status.running ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-700/50 text-slate-400'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${status.running ? 'bg-emerald-400' : 'bg-slate-500'}`} />
            {status.running ? t('collector.running') : t('collector.stopped')}
          </span>
          <button
            onClick={handleToggle}
            disabled={saving}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              status.is_enabled
                ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
            }`}
          >
            {status.is_enabled ? (
              <span className="flex items-center gap-1">
                <PowerOff className="h-3.5 w-3.5" /> {t('collector.disable')}
              </span>
            ) : (
              <span className="flex items-center gap-1">
                <Power className="h-3.5 w-3.5" /> {t('collector.enable')}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Status Info */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4 text-sm">
        <div>
          <span className="text-slate-400">{t('collector.totalStored')}</span>
          <p className="text-lg font-semibold text-slate-200">{status.total_queries_stored.toLocaleString()}</p>
        </div>
        <div>
          <span className="text-slate-400">{t('collector.lastPoll')}</span>
          <p className="text-slate-200">
            {status.last_poll_at
              ? new Date(status.last_poll_at).toLocaleString([], {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })
              : t('collector.never')}
          </p>
        </div>
      </div>

      {/* Error Display */}
      {status.last_error && (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {t('collector.lastError')} {status.last_error}
          {status.last_error_at && (
            <span className="text-red-400/70"> ({new Date(status.last_error_at).toLocaleString()})</span>
          )}
        </div>
      )}

      {/* Configuration */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 border-t border-slate-700/50 pt-4">
        <div>
          <label className="mb-1 block text-xs text-slate-400">{t('collector.pollInterval')}</label>
          <input
            type="number"
            min={10}
            max={300}
            value={pollInterval}
            onChange={(e) => setPollInterval(Number(e.target.value))}
            className="w-full rounded-lg border border-slate-700 bg-slate-800/80 py-1.5 px-3 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">{t('collector.retentionDays')}</label>
          <input
            type="number"
            min={1}
            max={365}
            value={retentionDays}
            onChange={(e) => setRetentionDays(Number(e.target.value))}
            className="w-full rounded-lg border border-slate-700 bg-slate-800/80 py-1.5 px-3 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
          />
        </div>
      </div>
      <div className="mt-3 flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${saving ? 'animate-spin' : ''}`} />
          {t('collector.save')}
        </button>
      </div>
    </div>
  );
}
