import { useTranslation } from 'react-i18next';

const WEEKDAYS = [
  { value: 0, label: 'Mo' },
  { value: 1, label: 'Di' },
  { value: 2, label: 'Mi' },
  { value: 3, label: 'Do' },
  { value: 4, label: 'Fr' },
  { value: 5, label: 'Sa' },
  { value: 6, label: 'So' },
];

interface ScheduleFormFieldsProps {
  scheduleType: string;
  scheduleTime: string;
  dayOfWeek: number;
  dayOfMonth: number;
  onChangeType: (type: string) => void;
  onChangeTime: (time: string) => void;
  onChangeDayOfWeek: (day: number) => void;
  onChangeDayOfMonth: (day: number) => void;
}

export function ScheduleFormFields({
  scheduleType,
  scheduleTime,
  dayOfWeek,
  dayOfMonth,
  onChangeType,
  onChangeTime,
  onChangeDayOfWeek,
  onChangeDayOfMonth,
}: ScheduleFormFieldsProps) {
  const { t } = useTranslation('settings');

  return (
    <>
      {/* Schedule Type */}
      <div>
        <label className="block text-sm text-slate-400 mb-1">{t('sync.scheduleType')}</label>
        <select
          value={scheduleType}
          onChange={(e) => onChangeType(e.target.value)}
          className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
        >
          <option value="daily">{t('sync.daily')}</option>
          <option value="weekly">{t('sync.weekly')}</option>
          <option value="monthly">{t('sync.monthly')}</option>
        </select>
      </div>

      {/* Time */}
      <div>
        <label className="block text-sm text-slate-400 mb-1">{t('sync.time')}</label>
        <input
          type="time"
          value={scheduleTime}
          onChange={(e) => onChangeTime(e.target.value)}
          className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
        />
      </div>

      {/* Day of Week (for weekly) */}
      {scheduleType === 'weekly' && (
        <div>
          <label className="block text-sm text-slate-400 mb-1">{t('sync.dayOfWeek')}</label>
          <div className="flex gap-1">
            {WEEKDAYS.map((day) => (
              <button
                key={day.value}
                type="button"
                onClick={() => onChangeDayOfWeek(day.value)}
                className={`flex-1 px-2 py-2 rounded-lg text-sm font-medium transition-colors ${
                  dayOfWeek === day.value
                    ? 'bg-sky-500 text-white'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                }`}
              >
                {day.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Day of Month (for monthly) */}
      {scheduleType === 'monthly' && (
        <div>
          <label className="block text-sm text-slate-400 mb-1">{t('sync.dayOfMonth')}</label>
          <select
            value={dayOfMonth}
            onChange={(e) => onChangeDayOfMonth(parseInt(e.target.value))}
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
          >
            {Array.from({ length: 31 }, (_, i) => i + 1).map((day) => (
              <option key={day} value={day}>{day}.</option>
            ))}
          </select>
        </div>
      )}
    </>
  );
}
