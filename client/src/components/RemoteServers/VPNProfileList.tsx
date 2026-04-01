import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import {
  Trash2,
  Loader2,
  Shield,
  RefreshCw,
  ChevronRight,
  QrCode,
} from 'lucide-react';
import * as api from '../../api/remote-servers';
import { VPNProfileExportDialog } from './VPNProfileExportDialog';

interface VPNProfileListProps {
  profiles: api.VPNProfile[];
  isLoading?: boolean;
  onTestConnection?: (id: number) => Promise<api.VPNConnectionTest>;
  onDelete?: (id: number) => Promise<void>;
}

export function VPNProfileList({
  profiles,
  isLoading = false,
  onTestConnection,
  onDelete,
}: VPNProfileListProps) {
  const { t } = useTranslation('remoteServers');
  const [testingId, setTestingId] = useState<number | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
  const [exportingId, setExportingId] = useState<number | null>(null);
  const [exportData, setExportData] = useState<api.VPNProfileExport | null>(null);
  const [exportOpen, setExportOpen] = useState(false);

  const handleTest = async (id: number) => {
    setTestingId(id);
    try {
      await onTestConnection?.(id);
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (window.confirm(t('vpn.deleteConfirm', { name }))) {
      try {
        setDeleteConfirm(id);
        await onDelete?.(id);
      } finally {
        setDeleteConfirm(null);
      }
    }
  };

  const handleExport = async (id: number) => {
    setExportingId(id);
    try {
      const data = await api.exportVPNProfile(id);
      setExportData(data);
      setExportOpen(true);
    } catch {
      toast.error(t('vpn.export.downloadFailed'));
    } finally {
      setExportingId(null);
    }
  };

  const getVpnTypeColor = (type: string) => {
    switch (type) {
      case 'openvpn':
        return 'bg-blue-100 text-blue-700';
      case 'wireguard':
        return 'bg-purple-100 text-purple-700';
      default:
        return 'bg-gray-100 text-gray-700';
    }
  };

  if (profiles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4">
        <div className="text-center max-w-md">
          <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mx-auto mb-4">
            <ChevronRight className="w-6 h-6 text-slate-500" />
          </div>
          <h3 className="text-lg font-medium text-white mb-2">{t('vpn.noProfiles')}</h3>
          <p className="text-sm text-slate-400">
            {t('vpn.noProfilesDescription')}
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-3">
        {profiles.map((profile) => (
        <div
          key={profile.id}
          className="bg-slate-800/60 border border-slate-700 rounded-lg p-4 hover:border-slate-600 transition-colors"
        >
          {/* Profile Header */}
          <div className="flex items-start justify-between mb-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-base font-semibold text-white truncate">{profile.name}</h3>
                <span className={`px-2 py-1 text-xs font-medium rounded ${getVpnTypeColor(profile.vpn_type)}`}>
                  {profile.vpn_type.toUpperCase()}
                </span>
                {profile.auto_connect && (
                  <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-700 rounded flex items-center gap-1">
                    <Shield className="w-3 h-3" />
                    Auto
                  </span>
                )}
              </div>
              {profile.description && (
                <p className="text-sm text-slate-400">{profile.description}</p>
              )}
            </div>
          </div>

          {/* Dates */}
          <div className="mb-3 text-xs text-slate-500 space-y-1">
            <p>{t('vpn.created')}: {new Date(profile.created_at).toLocaleString()}</p>
            <p>{t('vpn.updated')}: {new Date(profile.updated_at).toLocaleString()}</p>
          </div>

          {/* Actions */}
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => handleExport(profile.id)}
              disabled={isLoading || exportingId === profile.id}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-sky-500/20 text-sky-400 rounded hover:bg-sky-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title={t('vpn.export.button')}
            >
              {exportingId === profile.id ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <QrCode className="w-4 h-4" />
              )}
              {t('vpn.export.button')}
            </button>

            <button
              onClick={() => handleTest(profile.id)}
              disabled={isLoading || testingId === profile.id}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-slate-700 text-slate-300 rounded hover:bg-slate-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title={t('vpn.validateConfig')}
            >
              {testingId === profile.id ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              {t('vpn.validate')}
            </button>

            <button
              onClick={() => handleDelete(profile.id, profile.name)}
              disabled={isLoading || deleteConfirm === profile.id}
              className="ml-auto flex items-center gap-2 px-3 py-2 text-sm bg-red-500/20 text-red-400 rounded hover:bg-red-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title={t('vpn.deleteProfile')}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
        ))}
      </div>

      <VPNProfileExportDialog
        open={exportOpen}
        data={exportData}
        onClose={() => {
          setExportOpen(false);
          setExportData(null);
        }}
      />
    </>
  );
}
