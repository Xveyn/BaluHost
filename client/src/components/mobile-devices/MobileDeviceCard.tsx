import { useTranslation } from 'react-i18next';
import { Smartphone, Wifi, WifiOff, Calendar, Clock, User, Trash2 } from 'lucide-react';
import type { MobileDevice } from '../../api/mobile';
import { formatMobileDate, mobileTimeAgo, mobileExpiry } from './mobileDeviceDates';
import { NotificationStatus } from './NotificationStatus';

interface MobileDeviceCardProps {
  device: MobileDevice;
  isAdmin: boolean;
  onShowQr: (device: MobileDevice) => void;
  onDelete: (id: string, name: string) => void;
}

export function MobileDeviceCard({ device, isAdmin, onShowQr, onDelete }: MobileDeviceCardProps) {
  const { t } = useTranslation('common');

  return (
    <div
      key={device.id}
      className="p-3 sm:p-4 rounded-lg bg-slate-800/40 border border-slate-700/50 hover:border-slate-600/50 transition-colors cursor-pointer touch-manipulation active:scale-[0.99]"
      onClick={() => onShowQr(device)}
      title="Klicken um QR-Code anzuzeigen"
    >
      <div className="flex items-start justify-between gap-2 sm:gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 mb-2">
            <Smartphone className="w-4 h-4 sm:w-5 sm:h-5 text-sky-400 flex-shrink-0" />
            <h4 className="font-semibold text-sm sm:text-base text-white truncate">{device.device_name}</h4>
            {isAdmin && device.username && (
              <span className="flex items-center gap-1 text-[10px] sm:text-xs text-purple-400 bg-purple-400/10 px-1.5 sm:px-2 py-0.5 rounded-full">
                <User className="w-2.5 h-2.5 sm:w-3 sm:h-3" />
                {device.username}
              </span>
            )}
            {device.is_active ? (
              <span className="flex items-center gap-1 text-[10px] sm:text-xs text-green-400 bg-green-400/10 px-1.5 sm:px-2 py-0.5 rounded-full">
                <Wifi className="w-2.5 h-2.5 sm:w-3 sm:h-3" />
                Aktiv
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[10px] sm:text-xs text-slate-400 bg-slate-400/10 px-1.5 sm:px-2 py-0.5 rounded-full">
                <WifiOff className="w-2.5 h-2.5 sm:w-3 sm:h-3" />
                <span className="hidden sm:inline">Inaktiv</span>
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1 sm:gap-2 text-xs sm:text-sm text-slate-400">
            <div className="flex items-center gap-1 sm:gap-1.5">
              <span className="font-medium text-slate-300">Typ:</span>
              <span className="capitalize truncate">{device.device_type}</span>
            </div>
            {device.device_model && (
              <div className="flex items-center gap-1 sm:gap-1.5">
                <span className="font-medium text-slate-300">Modell:</span>
                <span className="truncate">{device.device_model}</span>
              </div>
            )}
            {device.os_version && (
              <div className="flex items-center gap-1 sm:gap-1.5 hidden sm:flex">
                <span className="font-medium text-slate-300">OS:</span>
                <span className="truncate">{device.os_version}</span>
              </div>
            )}
            {device.app_version && (
              <div className="flex items-center gap-1 sm:gap-1.5 hidden sm:flex">
                <span className="font-medium text-slate-300">App:</span>
                <span>v{device.app_version}</span>
              </div>
            )}
            <div className="flex items-center gap-1 sm:gap-1.5">
              <Calendar className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-slate-400" />
              <span className="font-medium text-slate-300 hidden sm:inline">Registriert:</span>
              <span className="truncate">{formatMobileDate(device.created_at)}</span>
            </div>
            <div className="flex items-center gap-1 sm:gap-1.5">
              <Clock className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-slate-400" />
              <span className="font-medium text-slate-300 hidden sm:inline">Zuletzt:</span>
              <span>{mobileTimeAgo(device.last_sync ?? device.last_seen ?? null, t)}</span>
            </div>
            {device.expires_at && (() => {
              const exp = mobileExpiry(device.expires_at);
              const { daysLeft, isExpired, isExpiringSoon } = exp;
              return (
                <div className={`flex flex-wrap items-center gap-1 sm:gap-1.5 col-span-1 sm:col-span-2 ${
                  isExpired ? 'text-red-400' : isExpiringSoon ? 'text-orange-400' : ''
                }`}>
                  <Calendar className="w-3 h-3 sm:w-3.5 sm:h-3.5" />
                  <span className="font-medium hidden sm:inline">Gültig bis:</span>
                  <span className="font-semibold truncate">{formatMobileDate(device.expires_at)}</span>
                  {isExpired && <span className="text-[10px] sm:text-xs bg-red-500/20 px-1.5 sm:px-2 py-0.5 rounded">Abgelaufen</span>}
                  {isExpiringSoon && !isExpired && <span className="text-[10px] sm:text-xs bg-orange-500/20 px-1.5 sm:px-2 py-0.5 rounded">{daysLeft}d</span>}
                </div>
              );
            })()}
          </div>

          {/* Notification Status */}
          <NotificationStatus deviceId={device.id} />
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation(); // Verhindere QR-Dialog
            onDelete(device.id, device.device_name);
          }}
          className="p-2 sm:p-2 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded-lg transition-colors touch-manipulation active:scale-95 min-w-[44px] min-h-[44px] flex items-center justify-center flex-shrink-0"
          title="Gerät löschen"
        >
          <Trash2 className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
