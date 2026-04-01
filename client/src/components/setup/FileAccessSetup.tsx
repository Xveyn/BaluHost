import { useState } from 'react';
import toast from 'react-hot-toast';
import { Folder, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { configureFileAccess } from '../../api/setup';
import { handleApiError } from '../../lib/errorHandling';

export interface FileAccessSetupProps {
  setupToken: string;
  onComplete: () => void;
}

export function FileAccessSetup({ setupToken, onComplete }: FileAccessSetupProps) {
  const [sambaEnabled, setSambaEnabled] = useState(true);
  const [sambaWorkgroup, setSambaWorkgroup] = useState('WORKGROUP');
  const [sambaExpanded, setSambaExpanded] = useState(false);

  const [webdavEnabled, setWebdavEnabled] = useState(false);
  const [webdavPort, setWebdavPort] = useState('8080');
  const [webdavExpanded, setWebdavExpanded] = useState(false);

  const [loading, setLoading] = useState(false);

  const atLeastOneEnabled = sambaEnabled || webdavEnabled;

  const handleSubmit = async () => {
    if (!atLeastOneEnabled) return;

    setLoading(true);
    try {
      const result = await configureFileAccess(
        {
          samba: sambaEnabled
            ? { enabled: true, workgroup: sambaWorkgroup.trim() || 'WORKGROUP' }
            : { enabled: false },
          webdav: webdavEnabled
            ? { enabled: true, port: parseInt(webdavPort, 10) || 8080 }
            : { enabled: false },
        },
        setupToken
      );

      const services = result.active_services.join(', ');
      toast.success(`Dateizugriff konfiguriert: ${services || 'keine Dienste aktiv'}`);
      onComplete();
    } catch (err) {
      handleApiError(err, 'Fehler beim Konfigurieren des Dateizugriffs');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-sky-500/20 flex items-center justify-center">
          <Folder className="w-5 h-5 text-sky-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Dateizugriff einrichten</h2>
          <p className="text-sm text-slate-400">
            Aktivieren Sie Netzwerkfreigaben für den Zugriff auf Dateien.
          </p>
        </div>
      </div>

      <div className="space-y-3 mb-6">
        {/* Samba Card */}
        <div
          className={`rounded-lg border transition-colors ${
            sambaEnabled
              ? 'border-sky-500/50 bg-sky-900/10'
              : 'border-slate-700 bg-slate-800/30'
          }`}
        >
          <div className="flex items-center justify-between p-4">
            <div className="flex items-center gap-3">
              <button
                type="button"
                role="switch"
                aria-checked={sambaEnabled}
                onClick={() => setSambaEnabled((v) => !v)}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2 focus:ring-offset-slate-900 ${
                  sambaEnabled ? 'bg-sky-500' : 'bg-slate-600'
                }`}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                    sambaEnabled ? 'translate-x-[18px]' : 'translate-x-1'
                  }`}
                />
              </button>
              <div>
                <p className="text-sm font-medium text-slate-100">Samba / SMB</p>
                <p className="text-xs text-slate-400">Windows-Netzwerkfreigabe (\\server\share)</p>
              </div>
            </div>
            {sambaEnabled && (
              <button
                type="button"
                onClick={() => setSambaExpanded((v) => !v)}
                className="text-slate-400 hover:text-slate-200 transition-colors"
              >
                {sambaExpanded ? (
                  <ChevronUp className="w-4 h-4" />
                ) : (
                  <ChevronDown className="w-4 h-4" />
                )}
              </button>
            )}
          </div>

          {sambaEnabled && sambaExpanded && (
            <div className="px-4 pb-4 pt-0 border-t border-slate-700/50">
              <div className="pt-4">
                <Input
                  label="Arbeitsgruppe"
                  value={sambaWorkgroup}
                  onChange={(e) => setSambaWorkgroup(e.target.value)}
                  placeholder="WORKGROUP"
                  helperText="Standard-Windows-Arbeitsgruppe. In den meisten Netzwerken 'WORKGROUP'."
                />
              </div>
            </div>
          )}
        </div>

        {/* WebDAV Card */}
        <div
          className={`rounded-lg border transition-colors ${
            webdavEnabled
              ? 'border-sky-500/50 bg-sky-900/10'
              : 'border-slate-700 bg-slate-800/30'
          }`}
        >
          <div className="flex items-center justify-between p-4">
            <div className="flex items-center gap-3">
              <button
                type="button"
                role="switch"
                aria-checked={webdavEnabled}
                onClick={() => setWebdavEnabled((v) => !v)}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2 focus:ring-offset-slate-900 ${
                  webdavEnabled ? 'bg-sky-500' : 'bg-slate-600'
                }`}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                    webdavEnabled ? 'translate-x-[18px]' : 'translate-x-1'
                  }`}
                />
              </button>
              <div>
                <p className="text-sm font-medium text-slate-100">WebDAV</p>
                <p className="text-xs text-slate-400">Zugriff über Browser & WebDAV-Clients</p>
              </div>
            </div>
            {webdavEnabled && (
              <button
                type="button"
                onClick={() => setWebdavExpanded((v) => !v)}
                className="text-slate-400 hover:text-slate-200 transition-colors"
              >
                {webdavExpanded ? (
                  <ChevronUp className="w-4 h-4" />
                ) : (
                  <ChevronDown className="w-4 h-4" />
                )}
              </button>
            )}
          </div>

          {webdavEnabled && webdavExpanded && (
            <div className="px-4 pb-4 pt-0 border-t border-slate-700/50">
              <div className="pt-4">
                <Input
                  label="Port"
                  type="number"
                  value={webdavPort}
                  onChange={(e) => setWebdavPort(e.target.value)}
                  placeholder="8080"
                  min="1024"
                  max="65535"
                  helperText="Standard-Port: 8080. Bereich: 1024–65535."
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {!atLeastOneEnabled && (
        <div className="flex gap-2 items-start rounded-lg border border-orange-700/50 bg-orange-900/10 p-3 mb-4">
          <AlertCircle className="w-4 h-4 text-orange-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-orange-300">
            Bitte aktivieren Sie mindestens einen Dateizugriffsdienst.
          </p>
        </div>
      )}

      <div className="pt-4 border-t border-slate-700 flex justify-end">
        <Button
          onClick={handleSubmit}
          loading={loading}
          disabled={!atLeastOneEnabled}
          size="lg"
        >
          Weiter
        </Button>
      </div>
    </div>
  );
}
