import { useState } from 'react';
import { Clock, Edit2, Trash2, X, Save } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { SyncSchedule, SyncDevice } from '../../api/sync';
import type { ScheduleFormData } from '../../hooks/useSyncSettings';
import { ScheduleFormFields } from './ScheduleFormFields';

const WEEKDAYS = [
  { value: 0, label: 'Mo' },
  { value: 1, label: 'Di' },
  { value: 2, label: 'Mi' },
  { value: 3, label: 'Do' },
  { value: 4, label: 'Fr' },
  { value: 5, label: 'Sa' },
  { value: 6, label: 'So' },
];

interface ScheduleListProps {
  schedules: SyncSchedule[];
  devices: SyncDevice[];
  onUpdate: (id: number, form: ScheduleFormData) => Promise<boolean>;
  onDisable: (id: number) => Promise<void>;
}

function formatDate(date: string | null) {
  if (!date) return 'N/A';
  return new Date(date).toLocaleString('de-DE');
}

function getDeviceName(devices: SyncDevice[], deviceId: string): string {
  return devices.find((d) => d.device_id === deviceId)?.device_name || deviceId;
}

function getScheduleDescription(schedule: SyncSchedule): string {
  let desc = schedule.time_of_day;
  if (schedule.schedule_type === 'weekly' && schedule.day_of_week != null) {
    const day = WEEKDAYS.find((d) => d.value === schedule.day_of_week);
    desc = `${day?.label || 'Mo'}, ${schedule.time_of_day}`;
  } else if (schedule.schedule_type === 'monthly' && schedule.day_of_month != null) {
    desc = `${schedule.day_of_month}., ${schedule.time_of_day}`;
  }
  return desc;
}

export function ScheduleList({ schedules, devices, onUpdate, onDisable }: ScheduleListProps) {
  const { t } = useTranslation('settings');

  const [editingSchedule, setEditingSchedule] = useState<SyncSchedule | null>(null);
  const [editType, setEditType] = useState('daily');
  const [editTime, setEditTime] = useState('02:00');
  const [editDayOfWeek, setEditDayOfWeek] = useState(0);
  const [editDayOfMonth, setEditDayOfMonth] = useState(1);
  const [isSaving, setIsSaving] = useState(false);

  function openEditModal(schedule: SyncSchedule) {
    setEditingSchedule(schedule);
    setEditType(schedule.schedule_type);
    setEditTime(schedule.time_of_day);
    setEditDayOfWeek(schedule.day_of_week ?? 0);
    setEditDayOfMonth(schedule.day_of_month ?? 1);
  }

  async function handleSave() {
    if (!editingSchedule) return;
    setIsSaving(true);
    const ok = await onUpdate(editingSchedule.schedule_id, {
      scheduleType: editType,
      scheduleTime: editTime,
      dayOfWeek: editDayOfWeek,
      dayOfMonth: editDayOfMonth,
    });
    setIsSaving(false);
    if (ok) setEditingSchedule(null);
  }

  return (
    <>
      <div>
        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Clock className="w-5 h-5" />
          {t('sync.activeSchedules')}
        </h3>
        {schedules.length === 0 ? (
          <div className="text-slate-400 text-center py-8">
            {t('sync.noSchedules')}
          </div>
        ) : (
          <div className="space-y-3">
            {schedules.map((schedule) => (
              <div
                key={schedule.schedule_id}
                className="p-4 bg-slate-800/50 border border-slate-700 rounded-lg flex items-center justify-between"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="font-medium text-slate-200">
                      {getDeviceName(devices, schedule.device_id)}
                    </span>
                    <span className="px-2 py-1 bg-sky-500/20 text-sky-400 text-xs rounded-full border border-sky-500/30">
                      {schedule.schedule_type}
                    </span>
                    <span className="text-sm text-slate-400">
                      {getScheduleDescription(schedule)}
                    </span>
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {t('sync.nextRun')}: {formatDate(schedule.next_run_at)} | {t('sync.lastRun')}: {formatDate(schedule.last_run_at)}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => openEditModal(schedule)}
                    className="p-2 text-sky-400 hover:bg-sky-500/10 rounded-lg transition-colors"
                    title="Edit schedule"
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => onDisable(schedule.schedule_id)}
                    className="p-2 text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                    title="Delete schedule"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Edit Modal */}
      {editingSchedule && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setEditingSchedule(null)}
          />
          <div className="relative z-10 w-full max-w-md rounded-lg bg-slate-900 shadow-xl">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
              <h3 className="text-lg font-medium text-white">{t('sync.editSchedule')}</h3>
              <button
                onClick={() => setEditingSchedule(null)}
                className="rounded-md p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Content */}
            <div className="px-6 py-4 space-y-4">
              <div className="text-sm text-slate-400">
                {t('sync.device')}: <span className="text-slate-200">{getDeviceName(devices, editingSchedule.device_id)}</span>
              </div>

              <ScheduleFormFields
                scheduleType={editType}
                scheduleTime={editTime}
                dayOfWeek={editDayOfWeek}
                dayOfMonth={editDayOfMonth}
                onChangeType={setEditType}
                onChangeTime={setEditTime}
                onChangeDayOfWeek={setEditDayOfWeek}
                onChangeDayOfMonth={setEditDayOfMonth}
              />
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-2 border-t border-slate-800 px-6 py-4">
              <button
                onClick={() => setEditingSchedule(null)}
                className="px-4 py-2 text-sm text-slate-300 hover:bg-slate-800 rounded-lg transition-colors"
              >
                {t('sync.cancel')}
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
              >
                <Save className="w-4 h-4" />
                {isSaving ? t('sync.saving') : t('sync.saveChanges')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
