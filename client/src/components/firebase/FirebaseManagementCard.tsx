import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Bell, Upload, Trash2, Loader2, AlertCircle, CheckCircle2, XCircle, Info, RefreshCw, Send, Smartphone } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getFirebaseStatus,
  uploadFirebaseCredentials,
  deleteFirebaseCredentials,
  sendTestNotification,
  type FirebaseStatus,
} from '../../api/firebase';
import { getAllDevices, type Device } from '../../api/devices';

export default function FirebaseManagementCard() {
  const { t } = useTranslation('system');
  const { t: tc } = useTranslation('common');
  const [status, setStatus] = useState<FirebaseStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [sendingTest, setSendingTest] = useState(false);
  const [testTitle, setTestTitle] = useState('');
  const [testBody, setTestBody] = useState('');
  const [testToken, setTestToken] = useState('');
  const [showTokenField, setShowTokenField] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchStatus = async () => {
    try {
      const data = await getFirebaseStatus();
      setStatus(data);
    } catch {
      toast.error(tc('toast.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  const fetchDevices = async () => {
    try {
      const all = await getAllDevices();
      setDevices(all.filter((d) => d.type === 'mobile' && d.is_active));
    } catch {
      // Non-critical — selector just stays empty
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchDevices();
  }, []);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Read and validate JSON client-side
    const text = await file.text();
    try {
      const parsed = JSON.parse(text);
      const required = ['type', 'project_id', 'private_key', 'client_email'];
      const missing = required.filter((f) => !(f in parsed));
      if (missing.length > 0) {
        toast.error(`${t('firebase.invalidJson')}: missing ${missing.join(', ')}`);
        return;
      }
    } catch {
      toast.error(t('firebase.invalidJson'));
      return;
    }

    setUploading(true);
    try {
      await uploadFirebaseCredentials(text);
      toast.success(t('firebase.uploadSuccess'));
      await fetchStatus();
    } catch {
      toast.error(t('firebase.uploadError'));
    } finally {
      setUploading(false);
      // Reset file input
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async () => {
    if (!confirm(t('firebase.deleteConfirm'))) return;

    setDeleting(true);
    try {
      await deleteFirebaseCredentials();
      toast.success(t('firebase.deleteSuccess'));
      await fetchStatus();
    } catch {
      toast.error(t('firebase.deleteError'));
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-400">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        {tc('loading')}
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Bell className="h-6 w-6 text-blue-400" />
            {t('firebase.title')}
          </h2>
          <p className="mt-1 text-sm text-slate-400">{t('firebase.subtitle')}</p>
        </div>
        <button
          onClick={() => { setLoading(true); fetchStatus(); }}
          className="flex items-center gap-1.5 rounded-lg bg-slate-800/50 px-3 py-2 text-sm text-slate-400 hover:bg-slate-700/50 hover:text-white transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          {tc('refresh')}
        </button>
      </div>

      {/* SDK Warning */}
      {!status.sdk_installed && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-4 text-amber-300 text-sm flex items-start gap-2">
          <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
          <span>{t('firebase.sdkWarning')}</span>
        </div>
      )}

      {/* Status Card */}
      <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5 space-y-4">
        <h3 className="text-base font-medium text-white">{t('firebase.status')}</h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Configuration Status */}
          <div className="flex items-center gap-2">
            <div className={`h-2.5 w-2.5 rounded-full ${status.configured ? 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.4)]' : 'bg-red-400'}`} />
            <span className={`text-sm font-medium ${status.configured ? 'text-green-400' : 'text-red-400'}`}>
              {status.configured ? t('firebase.configured') : t('firebase.notConfigured')}
            </span>
          </div>

          {/* Initialization Status */}
          <div className="flex items-center gap-2">
            {status.initialized
              ? <CheckCircle2 className="h-4 w-4 text-green-400" />
              : <XCircle className="h-4 w-4 text-slate-500" />
            }
            <span className={`text-sm ${status.initialized ? 'text-green-400' : 'text-slate-500'}`}>
              {status.initialized ? t('firebase.initialized') : t('firebase.notInitialized')}
            </span>
          </div>

          {/* SDK Status */}
          <div className="flex items-center gap-2">
            {status.sdk_installed
              ? <CheckCircle2 className="h-4 w-4 text-green-400" />
              : <XCircle className="h-4 w-4 text-amber-400" />
            }
            <span className={`text-sm ${status.sdk_installed ? 'text-slate-300' : 'text-amber-400'}`}>
              {status.sdk_installed ? t('firebase.sdkInstalled') : t('firebase.sdkNotInstalled')}
            </span>
          </div>

          {/* Source */}
          {status.credentials_source && (
            <div className="flex items-center gap-1.5 text-sm text-slate-400">
              <span className="text-slate-500">{t('firebase.source')}:</span>
              <span className="text-slate-300">
                {status.credentials_source === 'file' ? t('firebase.sourceFile') : t('firebase.sourceEnvVar')}
              </span>
            </div>
          )}
        </div>

        {/* Metadata (when configured) */}
        {status.configured && (
          <div className="border-t border-slate-700/50 pt-4 space-y-2">
            {status.project_id && (
              <div className="flex items-center gap-1.5 text-sm">
                <span className="text-slate-500">{t('firebase.projectId')}:</span>
                <code className="rounded bg-slate-900/50 px-2 py-0.5 text-xs font-mono text-blue-300 border border-slate-700/50">
                  {status.project_id}
                </code>
              </div>
            )}
            {status.client_email && (
              <div className="flex items-center gap-1.5 text-sm">
                <span className="text-slate-500">{t('firebase.serviceAccount')}:</span>
                <code className="rounded bg-slate-900/50 px-2 py-0.5 text-xs font-mono text-slate-300 border border-slate-700/50">
                  {status.client_email}
                </code>
              </div>
            )}
            {status.uploaded_at && (
              <div className="flex items-center gap-1.5 text-sm">
                <span className="text-slate-500">{t('firebase.uploadedAt')}:</span>
                <span className="text-slate-300">{new Date(status.uploaded_at).toLocaleString()}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Env var hint */}
      {status.credentials_source === 'env_var' && (
        <div className="rounded-lg bg-blue-500/10 border border-blue-500/20 p-4 text-blue-300 text-sm flex items-start gap-2">
          <Info className="h-5 w-5 shrink-0 mt-0.5" />
          <span>{t('firebase.envVarHint')}</span>
        </div>
      )}

      {/* Upload Section */}
      <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5 space-y-3">
        <h3 className="text-base font-medium text-white flex items-center gap-2">
          <Upload className="h-5 w-5 text-slate-400" />
          {t('firebase.uploadTitle')}
        </h3>
        <p className="text-sm text-slate-400">{t('firebase.uploadDescription')}</p>

        <div className="flex items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            onChange={handleFileSelect}
            disabled={uploading}
            className="hidden"
            id="firebase-upload"
          />
          <label
            htmlFor="firebase-upload"
            className={`flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors cursor-pointer ${
              uploading
                ? 'bg-slate-700/50 text-slate-500 cursor-not-allowed'
                : 'bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 border border-blue-500/40'
            }`}
          >
            {uploading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('firebase.uploading')}
              </>
            ) : (
              <>
                <Upload className="h-4 w-4" />
                {t('firebase.selectFile')}
              </>
            )}
          </label>
        </div>
      </div>

      {/* Test Notification Section (only when initialized) */}
      {status.initialized && (
        <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5 space-y-3">
          <h3 className="text-base font-medium text-white flex items-center gap-2">
            <Send className="h-5 w-5 text-emerald-400" />
            {t('firebase.testTitle')}
          </h3>
          <p className="text-sm text-slate-400">{t('firebase.testDescription')}</p>

          <div className="space-y-3">
            {/* Device selector */}
            <div>
              <label className="block text-xs text-slate-500 mb-1">
                <Smartphone className="inline h-3 w-3 mr-1" />
                {t('firebase.testDeviceLabel')}
              </label>
              <select
                value={selectedDeviceId}
                onChange={(e) => setSelectedDeviceId(e.target.value)}
                className="w-full rounded-lg bg-slate-900/50 border border-slate-700/50 px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none"
              >
                <option value="">{t('firebase.testDeviceAll')}</option>
                {devices.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}{d.username ? ` (${d.username})` : ''} — {d.platform}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t('firebase.testTitleLabel')}</label>
              <input
                type="text"
                value={testTitle}
                onChange={(e) => setTestTitle(e.target.value)}
                placeholder="BaluHost Test"
                className="w-full rounded-lg bg-slate-900/50 border border-slate-700/50 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-blue-500/50 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t('firebase.testBodyLabel')}</label>
              <input
                type="text"
                value={testBody}
                onChange={(e) => setTestBody(e.target.value)}
                placeholder={t('firebase.testBodyPlaceholder')}
                className="w-full rounded-lg bg-slate-900/50 border border-slate-700/50 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-blue-500/50 focus:outline-none"
              />
            </div>
            <div>
              <button
                type="button"
                onClick={() => setShowTokenField(!showTokenField)}
                className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                {showTokenField ? t('firebase.hideToken') : t('firebase.manualToken')}
              </button>
              {showTokenField && (
                <input
                  type="text"
                  value={testToken}
                  onChange={(e) => setTestToken(e.target.value)}
                  placeholder={t('firebase.tokenPlaceholder')}
                  className="mt-1 w-full rounded-lg bg-slate-900/50 border border-slate-700/50 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-blue-500/50 focus:outline-none font-mono text-xs"
                />
              )}
            </div>
          </div>

          <button
            onClick={async () => {
              setSendingTest(true);
              try {
                const res = await sendTestNotification({
                  title: testTitle || undefined,
                  body: testBody || undefined,
                  token: testToken || undefined,
                  device_id: selectedDeviceId || undefined,
                });
                if (res.success && res.sent_to > 0) {
                  toast.success(`${t('firebase.testSuccess')} (${res.sent_to})`);
                } else if (res.success) {
                  toast.success(res.message);
                } else {
                  toast.error(res.message);
                }
              } catch (err: any) {
                toast.error(err?.response?.data?.detail || t('firebase.testError'));
              } finally {
                setSendingTest(false);
              }
            }}
            disabled={sendingTest}
            className="flex items-center gap-2 rounded-lg bg-emerald-500/20 px-4 py-2.5 text-sm font-medium text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {sendingTest ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            {t('firebase.testSendButton')}
          </button>
        </div>
      )}

      {/* Delete Section (only when configured via file) */}
      {status.configured && status.credentials_source === 'file' && (
        <div className="rounded-xl bg-slate-800/50 border border-red-500/20 p-5 space-y-3">
          <h3 className="text-base font-medium text-white flex items-center gap-2">
            <Trash2 className="h-5 w-5 text-red-400" />
            {t('firebase.deleteTitle')}
          </h3>
          <p className="text-sm text-slate-400">{t('firebase.deleteDescription')}</p>

          <button
            onClick={handleDelete}
            disabled={deleting}
            className="flex items-center gap-2 rounded-lg bg-red-500/20 px-4 py-2.5 text-sm font-medium text-red-400 hover:bg-red-500/30 border border-red-500/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {deleting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
            {t('firebase.deleteButton')}
          </button>
        </div>
      )}
    </div>
  );
}
