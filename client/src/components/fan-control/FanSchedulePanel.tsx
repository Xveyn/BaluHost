import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Clock, Plus, Pencil, Trash2, Power, PowerOff } from 'lucide-react';
import toast from 'react-hot-toast';
import { useConfirmDialog } from '../../hooks/useConfirmDialog';
import type { FanScheduleEntry, FanInfo, CreateFanScheduleEntryRequest, UpdateFanScheduleEntryRequest } from '../../api/fan-control';
import {
  getFanSchedule,
  createFanScheduleEntry,
  updateFanScheduleEntry,
  deleteFanScheduleEntry,
  getActiveFanSchedule,
} from '../../api/fan-control';
import ScheduleTimeline from './ScheduleTimeline';
import ScheduleEntryForm from './ScheduleEntryForm';

interface FanSchedulePanelProps {
  fan: FanInfo;
  isReadOnly: boolean;
}

export default function FanSchedulePanel({ fan, isReadOnly }: FanSchedulePanelProps) {
  const { t } = useTranslation(['system', 'common']);
  const { confirm, dialog } = useConfirmDialog();

  const [entries, setEntries] = useState<FanScheduleEntry[]>([]);
  const [activeEntryId, setActiveEntryId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingEntry, setEditingEntry] = useState<FanScheduleEntry | undefined>();
  const [submitting, setSubmitting] = useState(false);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const fetchSchedule = useCallback(async () => {
    try {
      const [scheduleRes, activeRes] = await Promise.all([
        getFanSchedule(fan.fan_id),
        getActiveFanSchedule(fan.fan_id),
      ]);
      setEntries(scheduleRes.entries);
      setActiveEntryId(activeRes.active_entry?.id ?? null);
    } catch {
      // Silently handle — entries might not exist yet
    } finally {
      setLoading(false);
    }
  }, [fan.fan_id]);

  useEffect(() => {
    fetchSchedule();
  }, [fetchSchedule]);

  const handleCreate = async (data: CreateFanScheduleEntryRequest | UpdateFanScheduleEntryRequest) => {
    setSubmitting(true);
    try {
      await createFanScheduleEntry(fan.fan_id, data as CreateFanScheduleEntryRequest);
      toast.success(t('system:fanControl.schedule.messages.created', { name: (data as CreateFanScheduleEntryRequest).name }));
      setShowForm(false);
      await fetchSchedule();
    } catch {
      toast.error(t('system:fanControl.schedule.messages.createFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdate = async (data: CreateFanScheduleEntryRequest | UpdateFanScheduleEntryRequest) => {
    if (!editingEntry) return;
    setSubmitting(true);
    try {
      await updateFanScheduleEntry(fan.fan_id, editingEntry.id, data as UpdateFanScheduleEntryRequest);
      toast.success(t('system:fanControl.schedule.messages.updated'));
      setEditingEntry(undefined);
      setShowForm(false);
      await fetchSchedule();
    } catch {
      toast.error(t('system:fanControl.schedule.messages.updateFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (entry: FanScheduleEntry) => {
    const confirmed = await confirm(
      t('system:fanControl.schedule.deleteConfirmMessage', { name: entry.name }),
      {
        title: t('system:fanControl.schedule.deleteConfirmTitle'),
        variant: 'danger',
      }
    );
    if (!confirmed) return;

    try {
      await deleteFanScheduleEntry(fan.fan_id, entry.id);
      toast.success(t('system:fanControl.schedule.messages.deleted'));
      await fetchSchedule();
    } catch {
      toast.error(t('system:fanControl.schedule.messages.deleteFailed'));
    }
  };

  const handleToggle = async (entry: FanScheduleEntry) => {
    setTogglingId(entry.id);
    try {
      await updateFanScheduleEntry(fan.fan_id, entry.id, { is_enabled: !entry.is_enabled });
      await fetchSchedule();
    } catch {
      toast.error(t('system:fanControl.schedule.messages.toggleFailed'));
    } finally {
      setTogglingId(null);
    }
  };

  const handleEdit = (entry: FanScheduleEntry) => {
    setEditingEntry(entry);
    setShowForm(true);
  };

  const handleCancelForm = () => {
    setShowForm(false);
    setEditingEntry(undefined);
  };

  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="h-6 bg-slate-700 rounded w-48 mb-4" />
        <div className="h-10 bg-slate-800 rounded mb-4" />
        <div className="h-20 bg-slate-800 rounded" />
      </div>
    );
  }

  return (
    <div className="card">
      {dialog}

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <Clock className="w-6 h-6 text-sky-400" />
          {t('system:fanControl.schedule.title')}
        </h2>

        {!isReadOnly && entries.length < 8 && (
          <button
            onClick={() => { setEditingEntry(undefined); setShowForm(true); }}
            className="px-3 py-1.5 bg-sky-500 text-white rounded-lg hover:bg-sky-600 shadow-lg shadow-sky-500/30 text-sm flex items-center gap-1.5 transition-colors"
          >
            <Plus className="w-4 h-4" />
            {t('system:fanControl.schedule.addEntry')}
          </button>
        )}

        {!isReadOnly && entries.length >= 8 && (
          <span className="text-xs text-amber-400">
            {t('system:fanControl.schedule.maxEntriesReached')}
          </span>
        )}
      </div>

      <p className="text-sm text-slate-400 mb-4">
        {t('system:fanControl.schedule.description')}
      </p>

      {/* Timeline */}
      {entries.length > 0 && (
        <ScheduleTimeline entries={entries} activeEntryId={activeEntryId} />
      )}

      {/* Active status */}
      {entries.length > 0 && (
        <div className="mb-4">
          {activeEntryId ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              {t('system:fanControl.schedule.activeSchedule', {
                name: entries.find(e => e.id === activeEntryId)?.name ?? '?'
              })}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-700/50 border border-slate-600/30 text-slate-400 text-xs">
              {t('system:fanControl.schedule.usingDefaultCurve')}
            </span>
          )}
        </div>
      )}

      {/* Entry Form */}
      {showForm && (
        <div className="mb-4">
          <ScheduleEntryForm
            entry={editingEntry}
            onSubmit={editingEntry ? handleUpdate : handleCreate}
            onCancel={handleCancelForm}
            isSubmitting={submitting}
          />
        </div>
      )}

      {/* Entries List */}
      {entries.length === 0 && !showForm ? (
        <div className="text-center py-8">
          <Clock className="w-12 h-12 mx-auto text-slate-600 mb-3" />
          <p className="text-slate-400">{t('system:fanControl.schedule.noEntries')}</p>
          <p className="text-xs text-slate-500 mt-1">
            {t('system:fanControl.schedule.noEntriesHint')}
          </p>
        </div>
      ) : entries.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border border-slate-700 rounded-lg">
            <thead className="bg-slate-800">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-slate-400">{t('system:fanControl.schedule.name')}</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-slate-400">{t('system:fanControl.schedule.startTime')} – {t('system:fanControl.schedule.endTime')}</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-slate-400">{t('system:fanControl.schedule.curvePreset')}</th>
                <th className="px-4 py-2 text-center text-xs font-medium text-slate-400">{t('system:fanControl.schedule.priority')}</th>
                <th className="px-4 py-2 text-center text-xs font-medium text-slate-400"></th>
                {!isReadOnly && (
                  <th className="px-4 py-2 text-right text-xs font-medium text-slate-400"></th>
                )}
              </tr>
            </thead>
            <tbody>
              {entries.map(entry => {
                const isActive = entry.id === activeEntryId;
                return (
                  <tr key={entry.id} className={`border-t border-slate-700 ${!entry.is_enabled ? 'opacity-50' : ''}`}>
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-white font-medium">{entry.name}</span>
                        {isActive && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                            {t('system:fanControl.schedule.active')}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-sm text-slate-300 font-mono">
                      {entry.start_time} – {entry.end_time}
                      {entry.start_time > entry.end_time && (
                        <span className="ml-1 text-[10px] text-amber-400">
                          ({t('system:fanControl.schedule.overnight')})
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-sm text-slate-300">
                      {entry.curve_points.length} pts
                    </td>
                    <td className="px-4 py-2 text-center text-sm text-slate-300">
                      {entry.priority}
                    </td>
                    <td className="px-4 py-2 text-center">
                      {!entry.is_enabled && (
                        <span className="text-xs text-slate-500">
                          {t('system:fanControl.schedule.disabled')}
                        </span>
                      )}
                    </td>
                    {!isReadOnly && (
                      <td className="px-4 py-2">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleToggle(entry)}
                            disabled={togglingId === entry.id}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-300 hover:bg-slate-700 transition-colors"
                            title={entry.is_enabled ? 'Disable' : 'Enable'}
                          >
                            {togglingId === entry.id ? (
                              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-400 border-t-transparent" />
                            ) : entry.is_enabled ? (
                              <Power className="w-4 h-4 text-emerald-400" />
                            ) : (
                              <PowerOff className="w-4 h-4" />
                            )}
                          </button>
                          <button
                            onClick={() => handleEdit(entry)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-sky-400 hover:bg-slate-700 transition-colors"
                          >
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(entry)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-700 transition-colors"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
