import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { Activity, QrCode as QrCodeIcon, Calendar } from 'lucide-react';
import { useDeviceManagement } from '../hooks/useDeviceManagement';
import { DevicesTab, RegisterTab, SchedulesTab, EditDeviceModal, QrCodeDialog } from '../components/device-management';
import DesktopPairingDialog from '../components/DesktopPairingDialog';
import type { Device } from '../api/devices';
import type { MobileRegistrationToken } from '../api/mobile';

type Tab = 'devices' | 'register' | 'schedules';

export default function DeviceManagement() {
  const { t } = useTranslation(['devices', 'common']);
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<Tab>('devices');
  const [editingDevice, setEditingDevice] = useState<Device | null>(null);
  const [qrData, setQrData] = useState<MobileRegistrationToken | null>(null);
  const [showPairingDialog, setShowPairingDialog] = useState(false);

  const dm = useDeviceManagement();

  const handleQrClose = useCallback(() => {
    setQrData(null);
    dm.refetchDevices();
  }, [dm.refetchDevices]);

  // Auto-open pairing dialog if ?pair=1 is in URL
  useEffect(() => {
    if (searchParams.get('pair') === '1') {
      setShowPairingDialog(true);
      setSearchParams({}, { replace: true });
    }
  }, []);

  const tabClass = (tab: Tab) =>
    `flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition ${
      activeTab === tab
        ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
        : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
    }`;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">{t('description')}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={dm.refetchDevices}
            className="btn btn-secondary flex items-center gap-2 flex-1 sm:flex-initial justify-center touch-manipulation active:scale-95"
          >
            <Activity className="h-4 w-4" />
            <span>{t('buttons.refresh')}</span>
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-1">
        <div className="flex gap-2">
          <button onClick={() => setActiveTab('devices')} className={tabClass('devices')}>
            <Activity className="h-4 w-4" />
            <span className="hidden sm:inline">{t('tabs.devices')}</span>
          </button>
          <button onClick={() => setActiveTab('register')} className={tabClass('register')}>
            <QrCodeIcon className="h-4 w-4" />
            <span className="hidden sm:inline">{t('tabs.register')}</span>
            <span className="sm:hidden">{t('tabs.registerShort')}</span>
          </button>
          <button onClick={() => setActiveTab('schedules')} className={tabClass('schedules')}>
            <Calendar className="h-4 w-4" />
            <span className="hidden sm:inline">{t('tabs.schedules')}</span>
            <span className="sm:hidden">{t('tabs.schedulesShort')}</span>
          </button>
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'devices' && (
        <DevicesTab
          devices={dm.devices}
          mobileDevices={dm.mobileDevices}
          desktopDevices={dm.desktopDevices}
          stats={dm.stats}
          loading={dm.loading}
          error={dm.error}
          onEdit={setEditingDevice}
          onDelete={dm.handleDeleteDevice}
          onPair={() => setShowPairingDialog(true)}
        />
      )}

      {activeTab === 'register' && (
        <RegisterTab
          onGenerate={dm.handleGenerateToken}
          onTokenGenerated={setQrData}
        />
      )}

      {activeTab === 'schedules' && (
        <SchedulesTab
          devices={dm.devices}
          schedules={dm.schedules}
          schedulesLoading={dm.schedulesLoading}
          onCreateSchedule={dm.handleCreateSchedule}
          onDisableSchedule={dm.handleDisableSchedule}
          onEnableSchedule={dm.handleEnableSchedule}
        />
      )}

      {/* Modals */}
      <QrCodeDialog
        data={qrData}
        onClose={handleQrClose}
      />

      <EditDeviceModal
        device={editingDevice}
        onClose={() => setEditingDevice(null)}
        onSave={dm.handleSaveDeviceName}
      />

      <DesktopPairingDialog
        open={showPairingDialog}
        onClose={() => setShowPairingDialog(false)}
        onPaired={dm.refetchDevices}
      />

      {dm.confirmDialog}
    </div>
  );
}
