import { useState, useEffect } from 'react';
import { Upload, Wifi, Trash2, Check, AlertCircle, Download } from 'lucide-react';
import { apiClient } from '../lib/api';

interface FritzBoxConfig {
  id: number;
  endpoint: string;
  dns_servers: string;
  is_active: boolean;
  created_at: string;
}

export default function VpnManagement() {
  const [config, setConfig] = useState<FritzBoxConfig | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [publicEndpoint, setPublicEndpoint] = useState<string>('');
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [qrData, setQrData] = useState<string | null>(null);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await apiClient.get('/api/vpn/fritzbox/config');
      setConfig(response.data);
      
      // Load QR code data
      const qrResponse = await apiClient.get('/api/vpn/fritzbox/qr');
      setQrData(qrResponse.data.config_base64);
    } catch (err: any) {
      if (err.response?.status !== 404) {
        setError('Config konnte nicht geladen werden');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadFile(file);
      setError(null);
      setSuccess(null);
    }
  };

  const handleUpload = async () => {
    if (!uploadFile) return;

    try {
      setUploading(true);
      setError(null);
      setSuccess(null);

      // Read file content
      const fileContent = await uploadFile.text();

      // Upload to backend
      await apiClient.post('/api/vpn/fritzbox/upload', {
        config_content: fileContent,
        public_endpoint: publicEndpoint || undefined
      });

      setSuccess('Fritz!Box VPN-Konfiguration erfolgreich hochgeladen!');
      setUploadFile(null);
      setPublicEndpoint('');

      // Reload config
      await loadConfig();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload fehlgeschlagen');
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async () => {
    if (!config || !confirm('VPN-Konfiguration wirklich löschen?')) return;

    try {
      await apiClient.delete(`/api/vpn/fritzbox/config/${config.id}`);
      setSuccess('Konfiguration gelöscht');
      setConfig(null);
      setQrData(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Löschen fehlgeschlagen');
    }
  };

  const downloadConfig = () => {
    if (!qrData) return;
    
    try {
      // Decode Base64
      const configContent = atob(qrData);
      
      // Create blob and download
      const blob = new Blob([configContent], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'wireguard-config.conf';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError('Download fehlgeschlagen');
    }
  };

  if (loading) {
    return (
      <div className="text-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500 mx-auto"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Upload Section */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
          <Upload className="w-5 h-5 mr-2 text-sky-400" />
          Fritz!Box WireGuard Config hochladen
        </h3>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-start gap-2 text-red-400">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <span className="text-sm">{error}</span>
          </div>
        )}

        {success && (
          <div className="mb-4 p-3 bg-green-500/10 border border-green-500/30 rounded-lg flex items-start gap-2 text-green-400">
            <Check className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <span className="text-sm">{success}</span>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              WireGuard Konfigurationsdatei (.conf)
            </label>
            <input
              type="file"
              accept=".conf"
              onChange={handleFileSelect}
              className="block w-full text-sm rounded-lg border border-slate-700 bg-slate-800 text-slate-100 px-3 py-2 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-sky-500/20 file:text-sky-400 hover:file:bg-sky-500/30"
            />
            {uploadFile && (
              <p className="mt-2 text-sm text-slate-400">
                Ausgewählt: {uploadFile.name}
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Öffentlicher Endpoint <span className="text-slate-500">(optional)</span>
            </label>
            <input
              type="text"
              value={publicEndpoint}
              onChange={(e) => setPublicEndpoint(e.target.value)}
              placeholder="z.B. meinfritz.net oder 203.0.113.1"
              className="block w-full text-sm rounded-lg border border-slate-700 bg-slate-800 text-slate-100 px-3 py-2 focus:border-sky-500 focus:ring-1 focus:ring-sky-500 focus:outline-none"
            />
            <p className="mt-1 text-xs text-slate-400">
              Nur für Server-Configs notwendig (wenn kein Endpoint in der .conf enthalten ist).
              Format: DynDNS-Hostname oder IP-Adresse (ohne Port).
            </p>
          </div>

          <button
            onClick={handleUpload}
            disabled={!uploadFile || uploading}
            className="w-full sm:w-auto px-6 py-2.5 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploading ? 'Wird hochgeladen...' : 'Hochladen'}
          </button>
        </div>

        <div className="mt-4 p-3 bg-slate-800/50 border border-slate-700/50 rounded-lg">
          <p className="text-xs text-slate-400">
            💡 <strong>Hinweis:</strong> Die Fritz!Box-Konfiguration wird verschlüsselt gespeichert und über QR-Codes an mobile Geräte verteilt.
            Beim Generieren eines Mobile-Device-Tokens wird diese Config automatisch eingebettet, wenn "VPN einschließen" aktiviert ist.
          </p>
        </div>
      </div>

      {/* Current Config Display */}
      {config && (
        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold flex items-center text-white">
              <Wifi className="w-5 h-5 mr-2 text-green-400" />
              Aktive VPN-Konfiguration
            </h3>
            <div className="flex gap-2">
              <button
                onClick={downloadConfig}
                className="p-2 text-sky-400 hover:text-sky-300 transition-colors"
                title="Konfiguration herunterladen"
              >
                <Download className="w-5 h-5" />
              </button>
              <button
                onClick={handleDelete}
                className="p-2 text-red-400 hover:text-red-300 transition-colors"
                title="Konfiguration löschen"
              >
                <Trash2 className="w-5 h-5" />
              </button>
            </div>
          </div>

          <div className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-slate-400">Server-Endpoint:</span>
                <p className="text-white font-medium break-all">{config.endpoint}</p>
              </div>
              <div>
                <span className="text-slate-400">DNS-Server:</span>
                <p className="text-white font-medium">{config.dns_servers}</p>
              </div>
              <div>
                <span className="text-slate-400">Status:</span>
                <p className="text-green-400 font-medium flex items-center gap-1">
                  <Check className="w-4 h-4" /> Aktiv
                </p>
              </div>
              <div>
                <span className="text-slate-400">Hochgeladen am:</span>
                <p className="text-white font-medium">
                  {new Date(config.created_at).toLocaleString('de-DE')}
                </p>
              </div>
            </div>
          </div>

          <div className="mt-4 p-3 bg-sky-500/10 border border-sky-500/30 rounded-lg">
            <p className="text-xs text-sky-300">
              ✅ Diese Konfiguration wird automatisch an alle neuen Mobile-Geräte verteilt (wenn "VPN einschließen" aktiviert).
              Benutze die <strong>Mobile Devices</strong> Seite, um QR-Codes zu generieren.
            </p>
          </div>
        </div>
      )}

      {/* Info wenn keine Config */}
      {!config && !loading && (
        <div className="card border-slate-800/60 bg-slate-900/55 p-6">
          <div className="text-center text-slate-400">
            <Wifi className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p className="text-sm">
              Keine Fritz!Box VPN-Konfiguration vorhanden.
              <br />
              Lade eine .conf Datei hoch, um die VPN-Verteilung zu aktivieren.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
