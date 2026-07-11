import { Smartphone, Calendar, User, QrCode as QrCodeIcon, Trash2 } from 'lucide-react';
import type { MobileDevice } from '../../api/mobile';
import { formatMobileDate, mobileExpiry } from './mobileDeviceDates';

interface ExistingDeviceInfoViewProps {
  device: MobileDevice;
  isAdmin: boolean;
}

export function ExistingDeviceInfoView({ device, isAdmin }: ExistingDeviceInfoViewProps) {
  return (
    <>
      <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Smartphone className="w-5 h-5 text-amber-400" />
          <span className="text-amber-300 font-semibold">⚠️ Registriertes Gerät</span>
        </div>
        <p className="text-sm text-slate-300 mb-2">
          Dieses Gerät ist bereits bei BaluHost registriert und kann nicht erneut gescannt werden.
        </p>
        <p className="text-xs text-slate-400">
          Um das Gerät neu zu registrieren, lösche es zuerst mit dem Papierkorb-Symbol und generiere dann einen neuen QR-Code.
        </p>
      </div>

      <div className="bg-sky-500/10 border border-sky-500/30 rounded-lg p-4 mb-4">
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <Smartphone className="w-4 h-4 text-sky-400" />
            <span className="text-sky-300 font-medium">Geräte-Informationen</span>
          </div>
          {isAdmin && device.username && (
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-purple-400" />
              <span className="text-slate-300">Benutzer:</span>
              <span className="text-white font-semibold">{device.username}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-slate-400" />
            <span className="text-slate-300">Registriert:</span>
            <span className="text-white">{formatMobileDate(device.created_at)}</span>
          </div>
          {device.expires_at && (() => {
            const exp = mobileExpiry(device.expires_at);
            return (
              <div className={`flex items-center gap-2 ${
                exp.isExpired ? 'text-red-400' : exp.isExpiringSoon ? 'text-orange-400' : 'text-green-400'
              }`}>
                <Calendar className="w-4 h-4" />
                <span>Gültig bis:</span>
                <span className="font-semibold">{formatMobileDate(device.expires_at)}</span>
                {exp.isExpired ? (
                  <span className="text-xs bg-red-500/20 px-2 py-0.5 rounded">Abgelaufen</span>
                ) : exp.isExpiringSoon ? (
                  <span className="text-xs bg-orange-500/20 px-2 py-0.5 rounded">{exp.daysLeft} Tage</span>
                ) : (
                  <span className="text-xs bg-green-500/20 px-2 py-0.5 rounded">Aktiv</span>
                )}
              </div>
            );
          })()}
        </div>
      </div>

      <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 mb-4">
        <p className="text-xs text-slate-400 mb-2">📱 Verbindungs-Details:</p>
        <div className="space-y-1.5 text-xs font-mono text-slate-300">
          <div className="flex justify-between">
            <span className="text-slate-500">Server:</span>
            <span className="text-white">{window.location.origin}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Device ID:</span>
            <span className="text-white truncate ml-2">{device.id}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Status:</span>
            <span className={device.is_active ? 'text-green-400 font-semibold' : 'text-red-400'}>
              {device.is_active ? '● Aktiv' : '○ Inaktiv'}
            </span>
          </div>
        </div>
      </div>

      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
        <p className="text-sm font-semibold text-red-300 mb-2 flex items-center gap-2">
          <QrCodeIcon className="w-4 h-4" />
          So registrierst du das Gerät neu:
        </p>
        <ol className="list-decimal list-inside space-y-2 text-sm text-slate-300">
          <li>Klicke auf das <Trash2 className="inline w-3.5 h-3.5 mx-1 text-red-400" /> Papierkorb-Symbol bei diesem Gerät</li>
          <li>Bestätige die Löschung</li>
          <li>Generiere einen neuen QR-Code oben auf der Seite</li>
          <li>Scanne den neuen Code mit deiner BaluHost Mobile App</li>
        </ol>
      </div>
    </>
  );
}
