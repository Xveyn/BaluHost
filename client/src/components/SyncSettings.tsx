import { useState } from 'react';
import { Calendar, Smartphone, Settings } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSyncSettings } from '../hooks/useSyncSettings';
import { isTimeInSleepWindow } from '../lib/sleep-utils';
import {
  ScheduleFormFields,
  ScheduleList,
  BandwidthLimitsPanel,
  RegisteredDevicesPanel,
} from './sync-settings';

export default function SyncSettings() {
  const { t } = useTranslation('settings');
  const {
    devices,
    schedules,
    bandwidth,
    deviceFolders,
    sleepSchedule,
    handleCreateSchedule,
    handleUpdateSchedule,
    handleDisableSchedule,
    handleSaveBandwidth,
    handleRevokeVpn,
  } = useSyncSettings();

  // Create-form local state
  const [selectedDevice, setSelectedDevice] = useState('');
  const [scheduleType, setScheduleType] = useState('daily');
  const [scheduleTime, setScheduleTime] = useState('02:00');
  const [dayOfWeek, setDayOfWeek] = useState(0);
  const [dayOfMonth, setDayOfMonth] = useState(1);

  async function onCreate() {
    if (!selectedDevice) return;
    const ok = await handleCreateSchedule(selectedDevice, {
      scheduleType,
      scheduleTime,
      dayOfWeek,
      dayOfMonth,
    });
    if (ok) {
      setScheduleType('daily');
      setScheduleTime('02:00');
      setDayOfWeek(0);
      setDayOfMonth(1);
    }
  }

  return (
    <div className="space-y-6 w-full">
      <div className="rounded-lg shadow bg-slate-900/55 p-6">
        <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
          <Settings className="w-6 h-6" />
          {t('sync.title')}
        </h2>

        {/* Device Registration Info */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Smartphone className="w-5 h-5" />
            {t('sync.deviceRegistration')}
          </h3>
          <div className="text-slate-400 text-sm">
            {t('sync.deviceRegistrationInfo')}
            <div className="mt-2">
              {t('sync.manageDevicesFrom')} <a href="/mobile-devices" className="text-sky-400 underline">{t('sync.mobileAppsPage')}</a>
            </div>
          </div>
        </div>

        {/* Schedule Creation */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Calendar className="w-5 h-5" />
            {t('sync.createSchedule')}
          </h3>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Device Dropdown */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">{t('sync.device')}</label>
                <select
                  value={selectedDevice}
                  onChange={(e) => setSelectedDevice(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
                >
                  <option value="">{t('sync.selectDevice')}</option>
                  {devices.map((device) => (
                    <option key={device.device_id} value={device.device_id}>
                      {device.device_name} ({device.device_id.substring(0, 8)}...)
                    </option>
                  ))}
                </select>
              </div>

              <ScheduleFormFields
                scheduleType={scheduleType}
                scheduleTime={scheduleTime}
                dayOfWeek={dayOfWeek}
                dayOfMonth={dayOfMonth}
                onChangeType={setScheduleType}
                onChangeTime={setScheduleTime}
                onChangeDayOfWeek={setDayOfWeek}
                onChangeDayOfMonth={setDayOfMonth}
                sleepSchedule={sleepSchedule}
              />
            </div>

            <button
              onClick={onCreate}
              disabled={
                !selectedDevice ||
                (sleepSchedule?.enabled
                  ? isTimeInSleepWindow(scheduleTime, sleepSchedule.sleep_time, sleepSchedule.wake_time)
                  : false)
              }
              className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
            >
              {t('sync.createScheduleBtn')}
            </button>
          </div>
        </div>

        {/* Bandwidth */}
        <BandwidthLimitsPanel
          initialUpload={bandwidth?.upload_speed_limit ?? null}
          initialDownload={bandwidth?.download_speed_limit ?? null}
          onSave={handleSaveBandwidth}
        />

        {/* Schedules */}
        <ScheduleList
          schedules={schedules}
          devices={devices}
          onUpdate={handleUpdateSchedule}
          onDisable={handleDisableSchedule}
          sleepSchedule={sleepSchedule}
        />
      </div>

      {/* Registered Devices */}
      <RegisteredDevicesPanel
        devices={devices}
        deviceFolders={deviceFolders}
        onRevokeVpn={handleRevokeVpn}
      />
    </div>
  );
}
