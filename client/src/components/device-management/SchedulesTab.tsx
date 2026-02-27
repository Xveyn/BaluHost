import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Calendar, Clock, Plus, X } from 'lucide-react';
import { formatRelativeTime } from '../../lib/formatters';
import type { Device } from '../../api/devices';
import type { SyncSchedule, CreateScheduleRequest } from '../../api/sync';

interface SchedulesTabProps {
  devices: Device[];
  schedules: SyncSchedule[];
  schedulesLoading: boolean;
  onCreateSchedule: (data: CreateScheduleRequest) => Promise<boolean>;
  onDisableSchedule: (scheduleId: number) => void;
}

export function SchedulesTab({
  devices,
  schedules,
  schedulesLoading,
  onCreateSchedule,
  onDisableSchedule,
}: SchedulesTabProps) {
  const { t } = useTranslation(['devices', 'common']);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [scheduleType, setScheduleType] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const [timeOfDay, setTimeOfDay] = useState('02:00');
  const [dayOfWeek, setDayOfWeek] = useState<number | null>(null);
  const [dayOfMonth, setDayOfMonth] = useState<number | null>(null);

  const handleCreate = async () => {
    const ok = await onCreateSchedule({
      device_id: selectedDeviceId,
      schedule_type: scheduleType,
      time_of_day: timeOfDay,
      day_of_week: scheduleType === 'weekly' ? dayOfWeek : null,
      day_of_month: scheduleType === 'monthly' ? dayOfMonth : null,
      sync_deletions: true,
      resolve_conflicts: 'ask',
    });
    if (ok) {
      setSelectedDeviceId('');
      setScheduleType('daily');
      setTimeOfDay('02:00');
      setDayOfWeek(null);
      setDayOfMonth(null);
    }
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
            <select
              value={selectedDeviceId}
              onChange={(e) => setSelectedDeviceId(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
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
            <select
              value={scheduleType}
              onChange={(e) => setScheduleType(e.target.value as 'daily' | 'weekly' | 'monthly')}
              className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="daily">{t('schedules.daily')}</option>
              <option value="weekly">{t('schedules.weekly')}</option>
              <option value="monthly">{t('schedules.monthly')}</option>
            </select>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">{t('schedules.time')}</label>
            <input
              type="time"
              value={timeOfDay}
              onChange={(e) => setTimeOfDay(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
          </div>

          {scheduleType === 'weekly' && (
            <div>
              <label className="block text-xs text-slate-400 mb-1">{t('schedules.dayOfWeek')}</label>
              <select
                value={dayOfWeek ?? ''}
                onChange={(e) => setDayOfWeek(e.target.value ? parseInt(e.target.value) : null)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              >
                <option value="">{t('schedules.selectDay')}</option>
                <option value="0">{t('days.sunday')}</option>
                <option value="1">{t('days.monday')}</option>
                <option value="2">{t('days.tuesday')}</option>
                <option value="3">{t('days.wednesday')}</option>
                <option value="4">{t('days.thursday')}</option>
                <option value="5">{t('days.friday')}</option>
                <option value="6">{t('days.saturday')}</option>
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
                className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
            </div>
          )}

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
            const device = devices.find((d) => d.id === schedule.device_id);
            const deviceName = device?.name || schedule.device_id;

            return (
              <div
                key={schedule.schedule_id}
                className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 transition hover:border-amber-500/30"
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
                        {schedule.day_of_week !== null && schedule.day_of_week !== undefined && ` • ${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][schedule.day_of_week]}`}
                        {schedule.day_of_month !== null && schedule.day_of_month !== undefined && ` • Day ${schedule.day_of_month}`}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-medium ${
                        schedule.is_enabled
                          ? 'border border-emerald-500/40 bg-emerald-500/15 text-emerald-200'
                          : 'border border-slate-700/70 bg-slate-900/70 text-slate-400'
                      }`}
                    >
                      {schedule.is_enabled ? t('common:enabled') : t('common:disabled')}
                    </span>

                    {schedule.is_enabled && (
                      <button
                        onClick={() => onDisableSchedule(schedule.schedule_id)}
                        className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
                        title="Disable schedule"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>

                {schedule.next_run_at && (
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
    </div>
  );
}
