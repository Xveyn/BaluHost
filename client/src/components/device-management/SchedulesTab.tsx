import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Calendar, Clock, Plus, X, Check, Shield, Pencil, Trash2 } from 'lucide-react';
import { formatRelativeTime } from '../../lib/formatters';
import type { Device } from '../../api/devices';
import type { SyncSchedule, CreateScheduleRequest } from '../../api/sync';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const;

interface SchedulesTabProps {
  devices: Device[];
  schedules: SyncSchedule[];
  schedulesLoading: boolean;
  onCreateSchedule: (data: CreateScheduleRequest) => Promise<boolean>;
  onDisableSchedule: (scheduleId: number) => void;
  onEnableSchedule: (scheduleId: number) => void;
  onDeleteSchedule: (scheduleId: number) => void;
  onUpdateSchedule: (scheduleId: number, data: Record<string, unknown>) => Promise<boolean>;
}

function resolveDeviceName(devices: Device[], deviceId: string, backendName?: string | null): string {
  const device = devices.find((d) => d.id === deviceId);
  if (device) return device.name;
  if (backendName) return backendName;
  if (deviceId.length > 12) return `${deviceId.slice(0, 8)}… (unknown)`;
  return deviceId;
}

function WeekdayOptions({ t }: { t: (key: string) => string }) {
  return (
    <>
      <option value="">{t('schedules.selectDay')}</option>
      <option value="0">{t('days.monday')}</option>
      <option value="1">{t('days.tuesday')}</option>
      <option value="2">{t('days.wednesday')}</option>
      <option value="3">{t('days.thursday')}</option>
      <option value="4">{t('days.friday')}</option>
      <option value="5">{t('days.saturday')}</option>
      <option value="6">{t('days.sunday')}</option>
    </>
  );
}

const selectClass =
  'w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500';

export function SchedulesTab({
  devices,
  schedules,
  schedulesLoading,
  onCreateSchedule,
  onDisableSchedule,
  onEnableSchedule,
  onDeleteSchedule,
  onUpdateSchedule,
}: SchedulesTabProps) {
  const { t } = useTranslation(['devices', 'common']);

  // Create form state
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [scheduleType, setScheduleType] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const [timeOfDay, setTimeOfDay] = useState('02:00');
  const [dayOfWeek, setDayOfWeek] = useState<number | null>(null);
  const [dayOfMonth, setDayOfMonth] = useState<number | null>(null);
  const [autoVpn, setAutoVpn] = useState(false);

  // Edit modal state
  const [editingSchedule, setEditingSchedule] = useState<SyncSchedule | null>(null);
  const [editDeviceId, setEditDeviceId] = useState('');
  const [editType, setEditType] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const [editTime, setEditTime] = useState('02:00');
  const [editDayOfWeek, setEditDayOfWeek] = useState<number | null>(null);
  const [editDayOfMonth, setEditDayOfMonth] = useState<number | null>(null);
  const [editAutoVpn, setEditAutoVpn] = useState(false);
  const [editSaving, setEditSaving] = useState(false);

  const handleCreate = async () => {
    const ok = await onCreateSchedule({
      device_id: selectedDeviceId,
      schedule_type: scheduleType,
      time_of_day: timeOfDay,
      day_of_week: scheduleType === 'weekly' ? dayOfWeek : null,
      day_of_month: scheduleType === 'monthly' ? dayOfMonth : null,
      sync_deletions: true,
      resolve_conflicts: 'ask',
      auto_vpn: autoVpn,
    });
    if (ok) {
      setSelectedDeviceId('');
      setScheduleType('daily');
      setTimeOfDay('02:00');
      setDayOfWeek(null);
      setDayOfMonth(null);
      setAutoVpn(false);
    }
  };

  const openEdit = (schedule: SyncSchedule) => {
    setEditingSchedule(schedule);
    setEditDeviceId(schedule.device_id);
    setEditType(schedule.schedule_type as 'daily' | 'weekly' | 'monthly');
    setEditTime(schedule.time_of_day);
    setEditDayOfWeek(schedule.day_of_week ?? null);
    setEditDayOfMonth(schedule.day_of_month ?? null);
    setEditAutoVpn(schedule.auto_vpn ?? false);
  };

  const handleEditSave = async () => {
    if (!editingSchedule) return;
    setEditSaving(true);
    const updates: Record<string, unknown> = {
      schedule_type: editType,
      time_of_day: editTime,
      day_of_week: editType === 'weekly' ? editDayOfWeek : null,
      day_of_month: editType === 'monthly' ? editDayOfMonth : null,
      auto_vpn: editAutoVpn,
    };
    if (editDeviceId !== editingSchedule.device_id) {
      updates.device_id = editDeviceId;
    }
    const ok = await onUpdateSchedule(editingSchedule.schedule_id, updates);
    setEditSaving(false);
    if (ok) setEditingSchedule(null);
  };

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <div className="mb-4">
        <p className="text-xs uppercase tracking-[0.25em] text-slate-500">{t('schedules.title')}</p>
        <h2 className="mt-2 text-xl font-semibold text-white">
          {t('schedules.automatedSync', { count: schedules.length })}
        </h2>
      </div>

      {/* Create Schedule Form */}
      <div className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
        <h3 className="mb-3 text-sm font-medium text-slate-300 flex items-center gap-2">
          <Plus className="h-4 w-4" />
          {t('schedules.createNew')}
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">{t('schedules.device')}</label>
            <select value={selectedDeviceId} onChange={(e) => setSelectedDeviceId(e.target.value)} className={selectClass}>
              <option value="">{t('schedules.selectDevice')}</option>
              {devices.map((device) => (
                <option key={device.id} value={device.id}>
                  {device.name} ({device.type})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">{t('schedules.frequency')}</label>
            <select value={scheduleType} onChange={(e) => setScheduleType(e.target.value as 'daily' | 'weekly' | 'monthly')} className={selectClass}>
              <option value="daily">{t('schedules.daily')}</option>
              <option value="weekly">{t('schedules.weekly')}</option>
              <option value="monthly">{t('schedules.monthly')}</option>
            </select>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">{t('schedules.time')}</label>
            <input type="time" value={timeOfDay} onChange={(e) => setTimeOfDay(e.target.value)} className={selectClass} />
          </div>

          {scheduleType === 'weekly' && (
            <div>
              <label className="block text-xs text-slate-400 mb-1">{t('schedules.dayOfWeek')}</label>
              <select value={dayOfWeek ?? ''} onChange={(e) => setDayOfWeek(e.target.value ? parseInt(e.target.value) : null)} className={selectClass}>
                <WeekdayOptions t={t} />
              </select>
            </div>
          )}

          {scheduleType === 'monthly' && (
            <div>
              <label className="block text-xs text-slate-400 mb-1">{t('schedules.dayOfMonth')}</label>
              <input
                type="number"
                min="1"
                max="31"
                value={dayOfMonth ?? ''}
                onChange={(e) => setDayOfMonth(e.target.value ? parseInt(e.target.value) : null)}
                placeholder="1-31"
                className={selectClass}
              />
            </div>
          )}

          {/* Auto-VPN Toggle */}
          <div className="flex items-end">
            <label className="flex items-center gap-2 cursor-pointer w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2">
              <input
                type="checkbox"
                checked={autoVpn}
                onChange={(e) => setAutoVpn(e.target.checked)}
                className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500 focus:ring-offset-0"
              />
              <div className="flex items-center gap-1.5">
                <Shield className="h-3.5 w-3.5 text-sky-400" />
                <span className="text-sm text-slate-200">{t('schedules.autoVpn')}</span>
              </div>
            </label>
          </div>

          <div className="flex items-end">
            <button
              onClick={handleCreate}
              className="w-full rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-200 hover:border-emerald-500/50 hover:bg-emerald-500/20 touch-manipulation active:scale-95 flex items-center justify-center gap-2"
            >
              <Plus className="h-4 w-4" />
              {t('buttons.create')}
            </button>
          </div>
        </div>

        <p className="mt-2 text-xs text-slate-500">{t('schedules.autoVpnHint')}</p>
      </div>

      {/* Schedules List */}
      {schedulesLoading ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-center text-sm text-slate-500">
          {t('schedules.loadingSchedules')}
        </div>
      ) : schedules.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-center text-sm text-slate-500">
          {t('schedules.noSchedules')}
        </div>
      ) : (
        <div className="space-y-3">
          {schedules.map((schedule) => {
            const deviceName = resolveDeviceName(devices, schedule.device_id, schedule.device_name);
            const isEnabled = schedule.is_enabled !== false;

            return (
              <div
                key={schedule.schedule_id}
                className={`rounded-2xl border bg-slate-900/70 p-4 transition ${
                  isEnabled ? 'border-slate-800 hover:border-amber-500/30' : 'border-slate-800/50 opacity-60'
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950/70 text-amber-400 flex-shrink-0">
                      <Calendar className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-100 truncate">{deviceName}</p>
                      <p className="text-xs text-slate-500">
                        {schedule.schedule_type.charAt(0).toUpperCase() + schedule.schedule_type.slice(1)} at {schedule.time_of_day}
                        {schedule.day_of_week !== null && schedule.day_of_week !== undefined && ` • ${WEEKDAYS[schedule.day_of_week]}`}
                        {schedule.day_of_month !== null && schedule.day_of_month !== undefined && ` • Day ${schedule.day_of_month}`}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    {schedule.auto_vpn && (
                      <span className="rounded-full px-2.5 py-1 text-xs font-medium border border-sky-500/40 bg-sky-500/15 text-sky-200 flex items-center gap-1">
                        <Shield className="h-3 w-3" />
                        VPN
                      </span>
                    )}

                    <span
                      className={`rounded-full px-3 py-1 text-xs font-medium ${
                        isEnabled
                          ? 'border border-emerald-500/40 bg-emerald-500/15 text-emerald-200'
                          : 'border border-slate-700/70 bg-slate-900/70 text-slate-400'
                      }`}
                    >
                      {isEnabled ? t('common:enabled') : t('common:disabled')}
                    </span>

                    <button
                      onClick={() => openEdit(schedule)}
                      className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-2 text-sky-200 transition hover:border-sky-500/50 hover:bg-sky-500/20"
                      title={t('buttons.edit')}
                    >
                      <Pencil className="h-4 w-4" />
                    </button>

                    {isEnabled ? (
                      <button
                        onClick={() => onDisableSchedule(schedule.schedule_id)}
                        className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-2 text-amber-200 transition hover:border-amber-500/50 hover:bg-amber-500/20"
                        title={t('buttons.disable')}
                      >
                        <X className="h-4 w-4" />
                      </button>
                    ) : (
                      <button
                        onClick={() => onEnableSchedule(schedule.schedule_id)}
                        className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-2 text-emerald-200 transition hover:border-emerald-500/50 hover:bg-emerald-500/20"
                        title={t('buttons.enable')}
                      >
                        <Check className="h-4 w-4" />
                      </button>
                    )}

                    <button
                      onClick={() => onDeleteSchedule(schedule.schedule_id)}
                      className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
                      title={t('buttons.delete')}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {schedule.next_run_at && isEnabled && (
                  <div className="mt-3 flex items-center gap-2 text-xs text-slate-400">
                    <Clock className="h-3 w-3" />
                    <span>{t('schedules.nextRun')} {formatRelativeTime(schedule.next_run_at)}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Edit Modal */}
      {editingSchedule && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setEditingSchedule(null)}>
          <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-4 text-lg font-semibold text-white flex items-center gap-2">
              <Pencil className="h-5 w-5 text-sky-400" />
              {t('schedules.editSchedule')}
            </h3>

            <div className="space-y-4">
              <div>
                <label className="block text-xs text-slate-400 mb-1">{t('schedules.device')}</label>
                <select value={editDeviceId} onChange={(e) => setEditDeviceId(e.target.value)} className={selectClass}>
                  {!devices.some((d) => d.id === editingSchedule.device_id) && (
                    <option value={editingSchedule.device_id}>
                      {resolveDeviceName(devices, editingSchedule.device_id, editingSchedule.device_name)}
                    </option>
                  )}
                  {devices.map((device) => (
                    <option key={device.id} value={device.id}>
                      {device.name} ({device.type})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">{t('schedules.frequency')}</label>
                <select value={editType} onChange={(e) => setEditType(e.target.value as 'daily' | 'weekly' | 'monthly')} className={selectClass}>
                  <option value="daily">{t('schedules.daily')}</option>
                  <option value="weekly">{t('schedules.weekly')}</option>
                  <option value="monthly">{t('schedules.monthly')}</option>
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">{t('schedules.time')}</label>
                <input type="time" value={editTime} onChange={(e) => setEditTime(e.target.value)} className={selectClass} />
              </div>

              {editType === 'weekly' && (
                <div>
                  <label className="block text-xs text-slate-400 mb-1">{t('schedules.dayOfWeek')}</label>
                  <select value={editDayOfWeek ?? ''} onChange={(e) => setEditDayOfWeek(e.target.value ? parseInt(e.target.value) : null)} className={selectClass}>
                    <WeekdayOptions t={t} />
                  </select>
                </div>
              )}

              {editType === 'monthly' && (
                <div>
                  <label className="block text-xs text-slate-400 mb-1">{t('schedules.dayOfMonth')}</label>
                  <input
                    type="number"
                    min="1"
                    max="31"
                    value={editDayOfMonth ?? ''}
                    onChange={(e) => setEditDayOfMonth(e.target.value ? parseInt(e.target.value) : null)}
                    placeholder="1-31"
                    className={selectClass}
                  />
                </div>
              )}

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={editAutoVpn}
                  onChange={(e) => setEditAutoVpn(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500 focus:ring-offset-0"
                />
                <div className="flex items-center gap-1.5">
                  <Shield className="h-3.5 w-3.5 text-sky-400" />
                  <span className="text-sm text-slate-200">{t('schedules.autoVpn')}</span>
                </div>
              </label>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setEditingSchedule(null)}
                className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-slate-300 hover:bg-slate-700 transition"
              >
                {t('buttons.cancel')}
              </button>
              <button
                onClick={handleEditSave}
                disabled={editSaving}
                className="rounded-lg border border-sky-500/30 bg-sky-500/20 px-4 py-2 text-sm font-medium text-sky-200 hover:bg-sky-500/30 transition disabled:opacity-50"
              >
                {editSaving ? t('buttons.saving') : t('buttons.save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
