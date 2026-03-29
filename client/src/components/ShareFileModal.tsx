import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Users, Cloud, Loader2, ExternalLink } from 'lucide-react';
import toast from 'react-hot-toast';
import { createFileShare, type CreateFileShareRequest } from '../api/shares';
import { startCloudExport, checkConnectionScope } from '../api/cloud-export';
import { getConnections, type CloudConnection } from '../api/cloud-import';

interface ShareFileModalProps {
  fileId: number;
  fileName: string;
  filePath?: string;
  users: Array<{ id: number; username: string }>;
  onClose: () => void;
  onSuccess: () => void;
}

const ShareFileModal = ({ fileId, fileName, filePath, users, onClose, onSuccess }: ShareFileModalProps) => {
  const { t } = useTranslation(['shares', 'common']);
  const [activeTab, setActiveTab] = useState<'internal' | 'cloud'>('internal');
  const [loading, setLoading] = useState(false);

  // ─── Internal share state ────────────────────────────────────
  const [formData, setFormData] = useState<CreateFileShareRequest>({
    file_id: fileId,
    shared_with_user_id: 0,
    can_read: true,
    can_write: false,
    can_delete: false,
    can_share: false,
    expires_at: null,
  });

  // ─── Cloud export state ──────────────────────────────────────
  const [connections, setConnections] = useState<CloudConnection[]>([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState<number>(0);
  const [cloudFolder, setCloudFolder] = useState('BaluHost Shares/');
  const [linkType, setLinkType] = useState<'view' | 'edit'>('view');
  const [cloudExpiry, setCloudExpiry] = useState('');
  const [hasExportScope, setHasExportScope] = useState<boolean | null>(null);
  const [connectionsLoading, setConnectionsLoading] = useState(false);

  // Load cloud connections on mount
  useEffect(() => {
    setConnectionsLoading(true);
    getConnections()
      .then(conns => {
        const exportable = conns.filter(c => c.provider !== 'icloud' && c.is_active);
        setConnections(exportable);
        if (exportable.length > 0) setSelectedConnectionId(exportable[0].id);
      })
      .catch(() => setConnections([]))
      .finally(() => setConnectionsLoading(false));
  }, []);

  // Check scope when connection changes
  useEffect(() => {
    if (selectedConnectionId > 0) {
      setHasExportScope(null);
      checkConnectionScope(selectedConnectionId)
        .then(res => setHasExportScope(res.has_export_scope))
        .catch(() => setHasExportScope(false));
    }
  }, [selectedConnectionId]);

  // ─── Internal share submit ───────────────────────────────────
  const handleInternalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await createFileShare({
        ...formData,
        expires_at: formData.expires_at || null,
      });
      onSuccess();
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null;
      toast.error(detail || t('shares:toast.createShareFailed'));
    } finally {
      setLoading(false);
    }
  };

  // ─── Cloud export submit ─────────────────────────────────────
  const handleCloudSubmit = async () => {
    setLoading(true);
    try {
      await startCloudExport({
        connection_id: selectedConnectionId,
        source_path: filePath || fileName,
        cloud_folder: cloudFolder,
        link_type: linkType,
        expires_at: cloudExpiry || null,
      });
      toast.success(t('shares:cloudExport.exportStarted'));
      onSuccess();
    } catch {
      toast.error(t('shares:cloudExport.retryFailed', 'Failed to start export'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-white">
            {t('shares:modal.shareWithUser')}
          </h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* File name display */}
        <p className="text-sm text-slate-400 mb-4 truncate">
          {fileName}
        </p>

        {/* Tab Bar */}
        <div className="flex border-b border-slate-700 mb-4">
          <button
            type="button"
            onClick={() => setActiveTab('internal')}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'internal'
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Users className="w-4 h-4" />
            {t('shares:modal.tabInternal', 'Intern')}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('cloud')}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'cloud'
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Cloud className="w-4 h-4" />
            {t('shares:cloudExport.tab', 'Cloud Export')}
          </button>
        </div>

        {/* ─── Internal Tab ──────────────────────────────────── */}
        {activeTab === 'internal' && (
          <form onSubmit={handleInternalSubmit} className="space-y-4">
            {/* User Selection */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                {t('shares:modal.shareWithUser')}
              </label>
              <select
                value={formData.shared_with_user_id === 0 ? '' : String(formData.shared_with_user_id)}
                onChange={(e) =>
                  setFormData({ ...formData, shared_with_user_id: Number(e.target.value) })
                }
                className="w-full px-3 py-2 border border-slate-700 bg-slate-800/60 text-white rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                required
                disabled={users.length === 0}
              >
                <option value="" disabled>
                  {t('shares:form.selectUser')}
                </option>
                {(users ?? []).map((user) => (
                  <option key={user.id} value={String(user.id)}>
                    {user.username}
                  </option>
                ))}
              </select>
            </div>

            {/* Permissions */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                {t('shares:table.permissions')}
              </label>
              <div
                className={`bg-slate-800/30 rounded-lg p-3 border border-slate-700/50 space-y-2 ${
                  formData.shared_with_user_id === 0 ? 'opacity-50 pointer-events-none' : ''
                }`}
              >
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_read}
                    onChange={(e) => setFormData({ ...formData, can_read: e.target.checked })}
                    className="mr-2"
                    disabled={formData.shared_with_user_id === 0}
                  />
                  <span className="text-sm text-slate-300">
                    {t('shares:permissions.canRead')} ({t('shares:permissions.canReadDesc')})
                  </span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_write}
                    onChange={(e) => setFormData({ ...formData, can_write: e.target.checked })}
                    className="mr-2"
                    disabled={formData.shared_with_user_id === 0}
                  />
                  <span className="text-sm text-slate-300">
                    {t('shares:permissions.canWrite')} ({t('shares:permissions.canWriteDesc')})
                  </span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_delete}
                    onChange={(e) => setFormData({ ...formData, can_delete: e.target.checked })}
                    className="mr-2"
                    disabled={formData.shared_with_user_id === 0}
                  />
                  <span className="text-sm text-slate-300">{t('shares:permissions.canDelete')}</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.can_share}
                    onChange={(e) => setFormData({ ...formData, can_share: e.target.checked })}
                    className="mr-2"
                    disabled={formData.shared_with_user_id === 0}
                  />
                  <span className="text-sm text-slate-300">
                    {t('shares:permissions.canShare')} ({t('shares:permissions.canShareDesc')})
                  </span>
                </label>
              </div>
            </div>

            {/* Expiration Date */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                {t('shares:form.expirationDateOptional')}
              </label>
              <input
                type="datetime-local"
                value={formData.expires_at || ''}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    expires_at: e.target.value || null,
                  })
                }
                className="w-full px-3 py-2 border border-slate-700 bg-slate-800/60 text-white rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
              />
            </div>

            {/* Buttons */}
            <div className="flex justify-end space-x-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-slate-300 bg-slate-800/50 border border-slate-700 rounded-lg hover:bg-slate-700/50 transition-colors"
              >
                {t('shares:buttons.cancel')}
              </button>
              <button
                type="submit"
                disabled={loading || formData.shared_with_user_id === 0}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 touch-manipulation active:scale-95 transition-all"
              >
                {loading ? t('shares:buttons.sharing') : t('shares:buttons.share')}
              </button>
            </div>
          </form>
        )}

        {/* ─── Cloud Export Tab ───────────────────────────────── */}
        {activeTab === 'cloud' && (
          <div className="space-y-4">
            {connectionsLoading ? (
              <div className="flex items-center justify-center gap-2 py-10 text-slate-500">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>{t('common:loading', 'Loading...')}</span>
              </div>
            ) : connections.length === 0 ? (
              /* No connections hint */
              <div className="text-center py-8">
                <Cloud className="w-10 h-10 text-slate-600 mx-auto mb-3" />
                <p className="text-slate-400 text-sm mb-3">
                  {t('shares:cloudExport.noConnections', 'No cloud accounts connected.')}
                </p>
                <a
                  href="/cloud-import"
                  className="inline-flex items-center gap-1.5 text-sky-400 hover:text-sky-300 text-sm font-medium transition-colors"
                >
                  <ExternalLink className="w-4 h-4" />
                  {t('shares:cloudExport.goToCloudImport', 'Set up cloud connection')}
                </a>
              </div>
            ) : (
              <>
                {/* Provider dropdown */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    {t('shares:cloudExport.provider', 'Cloud Provider')}
                  </label>
                  <select
                    value={selectedConnectionId}
                    onChange={(e) => setSelectedConnectionId(Number(e.target.value))}
                    className="w-full px-3 py-2 border border-slate-700 bg-slate-800/60 text-white rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                  >
                    {connections.map((conn) => (
                      <option key={conn.id} value={conn.id}>
                        {conn.display_name} ({conn.provider === 'google_drive' ? 'Google Drive' : 'OneDrive'})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Scope check */}
                {hasExportScope === null && selectedConnectionId > 0 && (
                  <div className="flex items-center gap-2 text-slate-500 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t('shares:cloudExport.checkingScope', 'Checking permissions...')}
                  </div>
                )}

                {hasExportScope === false && (
                  <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3">
                    <p className="text-amber-300 text-sm mb-2">
                      {t('shares:cloudExport.scopeUpgradeNeeded', 'This connection needs additional permissions for file export.')}
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        window.open('/cloud-import', '_blank');
                      }}
                      className="inline-flex items-center gap-1.5 text-amber-400 hover:text-amber-300 text-sm font-medium transition-colors"
                    >
                      <ExternalLink className="w-4 h-4" />
                      {t('shares:cloudExport.upgradeScope', 'Upgrade permissions')}
                    </button>
                  </div>
                )}

                {/* Target folder */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    {t('shares:cloudExport.targetFolder', 'Target Folder')}
                  </label>
                  <input
                    type="text"
                    value={cloudFolder}
                    onChange={(e) => setCloudFolder(e.target.value)}
                    placeholder="BaluHost Shares/"
                    className="w-full px-3 py-2 border border-slate-700 bg-slate-800/60 text-white rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                  />
                </div>

                {/* Link type radio */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    {t('shares:cloudExport.linkType', 'Link Type')}
                  </label>
                  <div className="flex gap-4">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="linkType"
                        value="view"
                        checked={linkType === 'view'}
                        onChange={() => setLinkType('view')}
                        className="text-sky-500 focus:ring-sky-500"
                      />
                      <span className="text-sm text-slate-300">
                        {t('shares:cloudExport.viewOnly', 'View only')}
                      </span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="linkType"
                        value="edit"
                        checked={linkType === 'edit'}
                        onChange={() => setLinkType('edit')}
                        className="text-sky-500 focus:ring-sky-500"
                      />
                      <span className="text-sm text-slate-300">
                        {t('shares:cloudExport.canEdit', 'Can edit')}
                      </span>
                    </label>
                  </div>
                </div>

                {/* Expiration date */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    {t('shares:form.expirationDateOptional')}
                  </label>
                  <input
                    type="datetime-local"
                    value={cloudExpiry}
                    onChange={(e) => setCloudExpiry(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-700 bg-slate-800/60 text-white rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                  />
                </div>

                {/* Buttons */}
                <div className="flex justify-end space-x-3 pt-4">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 py-2 text-slate-300 bg-slate-800/50 border border-slate-700 rounded-lg hover:bg-slate-700/50 transition-colors"
                  >
                    {t('shares:buttons.cancel')}
                  </button>
                  <button
                    type="button"
                    onClick={handleCloudSubmit}
                    disabled={loading || selectedConnectionId === 0 || hasExportScope === false}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 touch-manipulation active:scale-95 transition-all"
                  >
                    {loading ? (
                      <span className="flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        {t('shares:cloudExport.exporting', 'Exporting...')}
                      </span>
                    ) : (
                      t('shares:cloudExport.startExport', 'Start Export')
                    )}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ShareFileModal;
