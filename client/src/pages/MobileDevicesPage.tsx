import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Smartphone, Plus, Trash2, RefreshCw, QrCode as QrCodeIcon, Wifi, WifiOff, Calendar, Clock, Bell, User } from 'lucide-react';
import { generateMobileToken, getMobileDevices, deleteMobileDevice, getDeviceNotifications, buildApiUrl, type MobileRegistrationToken, type MobileDevice, type ExpirationNotification } from '../lib/api';

interface UserInfo {
  id: string;
  username: string;
  email: string;
  role: string;
}

export default function MobileDevicesPage() {
  const { t } = useTranslation('common');
  const [user, setUser] = useState<UserInfo | null>(null);
  const [devices, setDevices] = useState<MobileDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0); // Force re-render trigger
  const [qrData, setQrData] = useState<MobileRegistrationToken | null>(null);
  const [showQrDialog, setShowQrDialog] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<MobileDevice | null>(null); // Für existierenden QR-Code
  const [includeVpn, setIncludeVpn] = useState(false);
  const [deviceName, setDeviceName] = useState('');
  const [tokenValidityDays, setTokenValidityDays] = useState(90);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    // User-Info aus Token laden
    const token = localStorage.getItem('token');
    if (token) {
      fetch(buildApiUrl('/api/auth/me'), {
        headers: { 'Authorization': `Bearer ${token}` }
      })
        .then(res => res.json())
        .then(data => setUser(data))
        .catch(err => console.error('Failed to load user:', err));
    }

    loadDevices();
    
    // Auto-refresh every 10 seconds to detect changes from mobile app
    const interval = setInterval(() => {
      loadDevices();
    }, 10000);
    
    return () => clearInterval(interval);
  }, []);

  const loadDevices = async () => {
    try {
      setLoading(true);
      console.log('Loading devices...');
      const data = await getMobileDevices();
      console.log('Loaded devices:', data);
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
      // Persist last generated token briefly so other UIs (SyncSettings) can auto-fill
      try {
        const stored = { ...token, device_name: deviceName.trim(), include_vpn: includeVpn };
        localStorage.setItem('lastMobileToken', JSON.stringify(stored));
      } catch (e) {
        console.warn('Failed to store lastMobileToken', e);
      }
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
      console.log('Deleting device:', deviceId);
      
      // Delete device from backend
      await deleteMobileDevice(deviceId);
      console.log('Device deleted successfully');
      
      // Force complete refresh
      setDevices([]);
      setRefreshKey(prev => prev + 1);
      await loadDevices();
      
    } catch (error) {
      console.error('Failed to delete device:', error);
      alert('Gerät konnte nicht gelöscht werden');
      await loadDevices();
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Nie';
    const date = new Date(dateString);
    return date.toLocaleString('de-DE');
  };

  const getTimeAgo = (dateString: string | null) => {
    if (!dateString) return t('time.never', 'Nie');
    const date = new Date(dateString);
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    
    if (seconds < 60) return t('time.justNow');
    if (seconds < 3600) return t('time.minutesAgo', { count: Math.floor(seconds / 60) });
    if (seconds < 86400) return t('time.hoursAgo', { count: Math.floor(seconds / 3600) });
    return t('time.daysAgo', { count: Math.floor(seconds / 86400) });
  };

  const handleShowDeviceQr = (device: MobileDevice) => {
    setSelectedDevice(device);
    setShowQrDialog(true);
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
                className="w-full h-3 sm:h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer slider-thumb touch-manipulation"
                style={{
                  background: `linear-gradient(to right, #38bdf8 0%, #38bdf8 ${((tokenValidityDays - 30) / 150) * 100}%, #334155 ${((tokenValidityDays - 30) / 150) * 100}%, #334155 100%)`
                }}
              />
              <div className="flex flex-col sm:flex-row items-center justify-between gap-1 sm:gap-2 text-xs">
                <span className="text-slate-400 hidden sm:inline">30 Tage</span>
                <span className="text-sky-400 font-semibold text-sm sm:text-base">
                  {tokenValidityDays} Tage ({Math.round(tokenValidityDays / 30)} Monate)
                </span>
                <span className="text-slate-400 hidden sm:inline">180 Tage</span>
                <span className="text-slate-400 sm:hidden text-[10px]">30 - 180 Tage</span>
              </div>
              <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-2 sm:p-3">
                <p className="text-[10px] sm:text-xs text-slate-400">
                  🔔 <strong>Auto-Erinnerungen:</strong> <span className="hidden sm:inline">Du wirst </span><strong>7 Tage</strong>, <strong>3 Tage</strong> & <strong>1 Stunde</strong> vor Ablauf benachrichtigt.
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
            className="w-full sm:w-auto px-6 py-2.5 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 touch-manipulation active:scale-95 min-h-[44px]"
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
            className="p-2 text-slate-400 hover:text-white transition-colors touch-manipulation active:scale-95 min-w-[44px] min-h-[44px] flex items-center justify-center"
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
          <div className="space-y-3" key={refreshKey}>
            {devices.map((device) => (
              <div
                key={`${device.id}-${refreshKey}`}
                className="p-3 sm:p-4 rounded-lg bg-slate-800/40 border border-slate-700/50 hover:border-slate-600/50 transition-colors cursor-pointer touch-manipulation active:scale-[0.99]"
                onClick={() => handleShowDeviceQr(device)}
                title="Klicken um QR-Code anzuzeigen"
              >
                <div className="flex items-start justify-between gap-2 sm:gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 mb-2">
                      <Smartphone className="w-4 h-4 sm:w-5 sm:h-5 text-sky-400 flex-shrink-0" />
                      <h4 className="font-semibold text-sm sm:text-base text-white truncate">{device.device_name}</h4>
                      {user?.role === 'admin' && device.username && (
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
                        <span className="truncate">{formatDate(device.created_at)}</span>
                      </div>
                      <div className="flex items-center gap-1 sm:gap-1.5">
                        <Clock className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-slate-400" />
                        <span className="font-medium text-slate-300 hidden sm:inline">Zuletzt:</span>
                        <span>{getTimeAgo(device.last_sync ?? device.last_seen ?? null)}</span>
                      </div>
                      {device.expires_at && (() => {
                        const expiresDate = new Date(device.expires_at);
                        const daysLeft = Math.ceil((expiresDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
                        const isExpiringSoon = daysLeft <= 7;
                        const isExpired = daysLeft <= 0;
                        return (
                          <div className={`flex flex-wrap items-center gap-1 sm:gap-1.5 col-span-1 sm:col-span-2 ${
                            isExpired ? 'text-red-400' : isExpiringSoon ? 'text-orange-400' : ''
                          }`}>
                            <Calendar className="w-3 h-3 sm:w-3.5 sm:h-3.5" />
                            <span className="font-medium hidden sm:inline">Gültig bis:</span>
                            <span className="font-semibold truncate">{formatDate(device.expires_at)}</span>
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
                      handleDeleteDevice(device.id, device.device_name);
                    }}
                    className="p-2 sm:p-2 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded-lg transition-colors touch-manipulation active:scale-95 min-w-[44px] min-h-[44px] flex items-center justify-center flex-shrink-0"
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
      {showQrDialog && (qrData || selectedDevice) && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-2 sm:p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-md h-full sm:h-auto max-h-[100vh] sm:max-h-[90vh] overflow-y-auto p-4 sm:p-6">
            <div className="flex items-center justify-between mb-4 gap-2">
              <h3 className="text-lg sm:text-xl font-semibold text-white truncate">
                {qrData ? 'QR-Code für Mobile App' : `QR-Code: ${selectedDevice?.device_name}`}
              </h3>
              <button
                onClick={() => {
                  setShowQrDialog(false);
                  setQrData(null);
                  setSelectedDevice(null);
                  setDeviceName('');
                  setIncludeVpn(false);
                  if (qrData) loadDevices(); // Nur bei neuem Token neu laden
                }}
                className="text-slate-400 hover:text-white transition-colors p-2 -mr-2 touch-manipulation active:scale-95 min-w-[44px] min-h-[44px] flex items-center justify-center flex-shrink-0"
              >
                ✕
              </button>
            </div>

            {qrData ? (
              // Neues Gerät
              <>
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
              </>
            ) : selectedDevice ? (
              // Existierendes Gerät - Info-Ansicht (kein Registrierungs-QR-Code!)
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
                    {user?.role === 'admin' && selectedDevice.username && (
                      <div className="flex items-center gap-2">
                        <User className="w-4 h-4 text-purple-400" />
                        <span className="text-slate-300">Benutzer:</span>
                        <span className="text-white font-semibold">{selectedDevice.username}</span>
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <Calendar className="w-4 h-4 text-slate-400" />
                      <span className="text-slate-300">Registriert:</span>
                      <span className="text-white">{formatDate(selectedDevice.created_at)}</span>
                    </div>
                    {selectedDevice.expires_at && (
                      <div className={`flex items-center gap-2 ${
                        (() => {
                          const expiresDate = new Date(selectedDevice.expires_at!);
                          const daysLeft = Math.ceil((expiresDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
                          const isExpired = daysLeft <= 0;
                          const isExpiringSoon = daysLeft <= 7;
                          return isExpired ? 'text-red-400' : isExpiringSoon ? 'text-orange-400' : 'text-green-400';
                        })()
                      }`}>
                        <Calendar className="w-4 h-4" />
                        <span>Gültig bis:</span>
                        <span className="font-semibold">{formatDate(selectedDevice.expires_at)}</span>
                        {(() => {
                          const expiresDate = new Date(selectedDevice.expires_at!);
                          const daysLeft = Math.ceil((expiresDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
                          const isExpired = daysLeft <= 0;
                          const isExpiringSoon = daysLeft <= 7;
                          if (isExpired) return <span className="text-xs bg-red-500/20 px-2 py-0.5 rounded">Abgelaufen</span>;
                          if (isExpiringSoon) return <span className="text-xs bg-orange-500/20 px-2 py-0.5 rounded">{daysLeft} Tage</span>;
                          return <span className="text-xs bg-green-500/20 px-2 py-0.5 rounded">Aktiv</span>;
                        })()}
                      </div>
                    )}
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
                      <span className="text-white truncate ml-2">{selectedDevice.id}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Status:</span> 
                      <span className={selectedDevice.is_active ? 'text-green-400 font-semibold' : 'text-red-400'}>
                        {selectedDevice.is_active ? '● Aktiv' : '○ Inaktiv'}
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
            ) : null}
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
