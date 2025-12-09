import { useState, useEffect } from 'react';
import { Smartphone, Plus, Trash2, RefreshCw, QrCode as QrCodeIcon, Wifi, WifiOff, Calendar, Clock, Bell } from 'lucide-react';
import { generateMobileToken, getMobileDevices, deleteMobileDevice, getDeviceNotifications, type MobileRegistrationToken, type MobileDevice, type ExpirationNotification } from '../lib/api';

export default function MobileDevicesPage() {
  const [devices, setDevices] = useState<MobileDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [qrData, setQrData] = useState<MobileRegistrationToken | null>(null);
  const [showQrDialog, setShowQrDialog] = useState(false);
  const [includeVpn, setIncludeVpn] = useState(false);
  const [deviceName, setDeviceName] = useState('');
  const [tokenValidityDays, setTokenValidityDays] = useState(90);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    loadDevices();
  }, []);

  const loadDevices = async () => {
    try {
      setLoading(true);
      const data = await getMobileDevices();
      setDevices(data);
    } catch (error) {
      console.error('Failed to load devices:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateToken = async () => {
    if (!deviceName.trim()) {
      alert('Bitte Gerätenamen eingeben');
      return;
    }

    try {
      setGenerating(true);
      const token = await generateMobileToken(includeVpn, deviceName.trim(), tokenValidityDays);
      setQrData(token);
      setShowQrDialog(true);
    } catch (error: any) {
      console.error('Failed to generate token:', error);
      const errorMsg = error?.response?.data?.detail || 'QR-Code konnte nicht generiert werden';
      alert(errorMsg);
    } finally {
      setGenerating(false);
    }
  };

  const handleDeleteDevice = async (deviceId: string, deviceName: string) => {
    if (!confirm(`Gerät "${deviceName}" wirklich löschen?`)) {
      return;
    }

    try {
      await deleteMobileDevice(deviceId);
      await loadDevices();
    } catch (error) {
      console.error('Failed to delete device:', error);
      alert('Gerät konnte nicht gelöscht werden');
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Nie';
    const date = new Date(dateString);
    return date.toLocaleString('de-DE');
  };

  const getTimeAgo = (dateString: string | null) => {
    if (!dateString) return 'Nie';
    const date = new Date(dateString);
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    
    if (seconds < 60) return 'Gerade eben';
    if (seconds < 3600) return `Vor ${Math.floor(seconds / 60)} Min`;
    if (seconds < 86400) return `Vor ${Math.floor(seconds / 3600)} Std`;
    return `Vor ${Math.floor(seconds / 86400)} Tagen`;
  };

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <h1 className="text-2xl sm:text-3xl font-semibold text-white mb-2">Mobile Geräte</h1>
        <p className="text-sm text-slate-400">Verwalte deine mobilen BaluHost-Apps</p>
      </div>

      {/* Generate Token Card */}
      <div className="card border-slate-800/60 bg-slate-900/55 mb-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
          <QrCodeIcon className="w-5 h-5 mr-2 text-sky-400" />
          Neues Gerät registrieren
        </h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Gerätename
            </label>
            <input
              type="text"
              value={deviceName}
              onChange={(e) => setDeviceName(e.target.value)}
              placeholder="z.B. iPhone 15, Samsung Galaxy S24"
              className="input w-full"
            />
          </div>
          
          {/* Token Validity Slider */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Gültigkeitsdauer der Autorisierung
            </label>
            <div className="space-y-2">
              <input
                type="range"
                min="30"
                max="180"
                step="1"
                value={tokenValidityDays}
                onChange={(e) => setTokenValidityDays(Number(e.target.value))}
                className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer slider-thumb"
                style={{
                  background: `linear-gradient(to right, #38bdf8 0%, #38bdf8 ${((tokenValidityDays - 30) / 150) * 100}%, #334155 ${((tokenValidityDays - 30) / 150) * 100}%, #334155 100%)`
                }}
              />
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">30 Tage (Minimum)</span>
                <span className="text-sky-400 font-semibold text-base">
                  {tokenValidityDays} Tage ({Math.round(tokenValidityDays / 30)} Monate)
                </span>
                <span className="text-slate-400">180 Tage (Maximum)</span>
              </div>
              <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-3">
                <p className="text-xs text-slate-400">
                  🔔 <strong>Automatische Benachrichtigungen:</strong> Du wirst <strong>7 Tage</strong>, <strong>3 Tage</strong> und <strong>1 Stunde</strong> vor Ablauf per Push-Benachrichtigung erinnert. Nach Ablauf wird das Gerät automatisch deautorisiert.
                </p>
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="includeVpn"
              checked={includeVpn}
              onChange={(e) => setIncludeVpn(e.target.checked)}
              className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-sky-500 focus:ring-sky-500"
            />
            <label htmlFor="includeVpn" className="text-sm text-slate-300">
              VPN-Konfiguration einschließen (WireGuard)
            </label>
          </div>
          <button
            onClick={handleGenerateToken}
            disabled={generating || !deviceName.trim()}
            className="w-full sm:w-auto px-6 py-2.5 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {generating ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Generiere...
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                QR-Code generieren
              </>
            )}
          </button>
        </div>
      </div>

      {/* Devices List */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white flex items-center">
            <Smartphone className="w-5 h-5 mr-2 text-sky-400" />
            Registrierte Geräte ({devices.length})
          </h3>
          <button
            onClick={loadDevices}
            disabled={loading}
            className="p-2 text-slate-400 hover:text-white transition-colors"
            title="Aktualisieren"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {loading ? (
          <div className="text-center py-8 text-slate-400">
            <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-2" />
            Lade Geräte...
          </div>
        ) : devices.length === 0 ? (
          <div className="text-center py-8 text-slate-400">
            <Smartphone className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>Keine Geräte registriert</p>
            <p className="text-sm mt-1">Generiere einen QR-Code, um dein erstes Gerät hinzuzufügen</p>
          </div>
        ) : (
          <div className="space-y-3">
            {devices.map((device) => (
              <div
                key={device.id}
                className="p-4 rounded-lg bg-slate-800/40 border border-slate-700/50 hover:border-slate-600/50 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <Smartphone className="w-5 h-5 text-sky-400 flex-shrink-0" />
                      <h4 className="font-semibold text-white truncate">{device.device_name}</h4>
                      {device.is_active ? (
                        <span className="flex items-center gap-1 text-xs text-green-400 bg-green-400/10 px-2 py-0.5 rounded-full">
                          <Wifi className="w-3 h-3" />
                          Aktiv
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-xs text-slate-400 bg-slate-400/10 px-2 py-0.5 rounded-full">
                          <WifiOff className="w-3 h-3" />
                          Inaktiv
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm text-slate-400">
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium text-slate-300">Typ:</span>
                        <span className="capitalize">{device.device_type}</span>
                      </div>
                      {device.device_model && (
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-slate-300">Modell:</span>
                          <span>{device.device_model}</span>
                        </div>
                      )}
                      {device.os_version && (
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-slate-300">OS:</span>
                          <span>{device.os_version}</span>
                        </div>
                      )}
                      {device.app_version && (
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-slate-300">App:</span>
                          <span>v{device.app_version}</span>
                        </div>
                      )}
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                        <span className="font-medium text-slate-300">Registriert:</span>
                        <span>{formatDate(device.created_at)}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5 text-slate-400" />
                        <span className="font-medium text-slate-300">Zuletzt:</span>
                        <span>{getTimeAgo(device.last_sync)}</span>
                      </div>
                      {device.expires_at && (() => {
                        const expiresDate = new Date(device.expires_at);
                        const daysLeft = Math.ceil((expiresDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
                        const isExpiringSoon = daysLeft <= 7;
                        const isExpired = daysLeft <= 0;
                        return (
                          <div className={`flex items-center gap-1.5 col-span-2 ${
                            isExpired ? 'text-red-400' : isExpiringSoon ? 'text-orange-400' : ''
                          }`}>
                            <Calendar className="w-3.5 h-3.5" />
                            <span className="font-medium">Gültig bis:</span>
                            <span className="font-semibold">{formatDate(device.expires_at)}</span>
                            {isExpired && <span className="text-xs bg-red-500/20 px-2 py-0.5 rounded">Abgelaufen</span>}
                            {isExpiringSoon && !isExpired && <span className="text-xs bg-orange-500/20 px-2 py-0.5 rounded">Läuft bald ab ({daysLeft} Tage)</span>}
                          </div>
                        );
                      })()}
                    </div>
                    
                    {/* Notification Status */}
                    <NotificationStatus deviceId={device.id} />
                  </div>
                  <button
                    onClick={() => handleDeleteDevice(device.id, device.device_name)}
                    className="p-2 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded-lg transition-colors"
                    title="Gerät löschen"
                  >
                    <Trash2 className="w-5 h-5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* QR Code Dialog */}
      {showQrDialog && qrData && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-semibold text-white">QR-Code für Mobile App</h3>
              <button
                onClick={() => {
                  setShowQrDialog(false);
                  setQrData(null);
                  setDeviceName('');
                  setIncludeVpn(false);
                  loadDevices();
                }}
                className="text-slate-400 hover:text-white transition-colors"
              >
                ✕
              </button>
            </div>

            <div className="bg-white p-4 rounded-lg mb-4">
              <img
                src={`data:image/png;base64,${qrData.qr_code}`}
                alt="QR Code"
                className="w-full h-auto"
              />
            </div>

            <div className="space-y-2 text-sm text-slate-300 mb-4">
              <p>✓ Scanne diesen QR-Code mit der BaluHost Mobile App</p>
              <p>✓ Registrierungs-Token ist <strong>5 Minuten</strong> gültig</p>
              <p>✓ Geräte-Autorisierung gilt für <strong className="text-sky-400">{qrData.device_token_validity_days} Tage ({Math.round(qrData.device_token_validity_days / 30)} Monate)</strong></p>
              {qrData.vpn_config && (
                <p className="text-green-400">✓ VPN-Konfiguration eingeschlossen</p>
              )}
            </div>

            <div className="bg-sky-500/10 border border-sky-500/30 rounded-lg p-3 mb-4">
              <p className="text-xs text-sky-300 font-semibold mb-1.5 flex items-center gap-1.5">
                🔔 Automatische Erinnerungen
              </p>
              <p className="text-xs text-slate-300">
                Du wirst <strong>7 Tage</strong>, <strong>3 Tage</strong> und <strong>1 Stunde</strong> vor Ablauf per Push-Benachrichtigung erinnert.
              </p>
            </div>

            <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3">
              <p className="text-xs text-slate-400 mb-1">Token läuft ab:</p>
              <p className="text-sm text-white font-mono">
                {new Date(qrData.expires_at).toLocaleString('de-DE')}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Component to display last notification sent to device.
 */
function NotificationStatus({ deviceId }: { deviceId: string }) {
  const [lastNotification, setLastNotification] = useState<ExpirationNotification | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const loadNotification = async () => {
      try {
        setLoading(true);
        const notifications = await getDeviceNotifications(deviceId, 1);
        if (notifications.length > 0) {
          setLastNotification(notifications[0]);
        }
      } catch (error) {
        console.error('Failed to load notifications:', error);
      } finally {
        setLoading(false);
      }
    };

    loadNotification();
  }, [deviceId]);

  if (loading || !lastNotification) return null;

  const notificationLabels: Record<string, string> = {
    '7_days': '7 Tage Warnung',
    '3_days': '3 Tage Warnung',
    '1_hour': '1 Stunde Warnung'
  };

  const notificationLabel = notificationLabels[lastNotification.notification_type] || lastNotification.notification_type;
  const sentDate = new Date(lastNotification.sent_at);
  const timeAgo = (() => {
    const seconds = Math.floor((Date.now() - sentDate.getTime()) / 1000);
    if (seconds < 60) return 'Gerade eben';
    if (seconds < 3600) return `Vor ${Math.floor(seconds / 60)} Min`;
    if (seconds < 86400) return `Vor ${Math.floor(seconds / 3600)} Std`;
    return `Vor ${Math.floor(seconds / 86400)} Tagen`;
  })();

  return (
    <div className="mt-3 pt-3 border-t border-slate-700/50">
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <Bell className={`w-3.5 h-3.5 ${
          lastNotification.success ? 'text-sky-400' : 'text-red-400'
        }`} />
        <span className="font-medium text-slate-300">Letzte Benachrichtigung:</span>
        <span>{notificationLabel}</span>
        <span className="text-slate-500">•</span>
        <span>{timeAgo}</span>
        {!lastNotification.success && (
          <span className="text-red-400 font-semibold">Fehlgeschlagen</span>
        )}
      </div>
    </div>
  );
}
