import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  X,
  Folder,
  File as FileIcon,
  ChevronRight,
  ArrowLeft,
  Loader2,
  AlertCircle,
  Check,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { createFileShare, type CreateFileShareRequest } from '../api/shares';
import { apiClient } from '../lib/api';
import { formatBytes } from '../lib/formatters';

interface ExplorerFile {
  name: string;
  path: string;
  type: string;
  size?: number;
  file_id?: number;
}

interface CreateFileShareModalProps {
  fileId?: number;
  users: Array<{ id: number; username: string }>;
  onClose: () => void;
  onSuccess: () => void;
}

const CreateFileShareModal = ({ fileId, users, onClose, onSuccess }: CreateFileShareModalProps) => {
  const { t } = useTranslation(['shares', 'common']);
  const [loading, setLoading] = useState(false);
  const [explorerPath, setExplorerPath] = useState('');
  const [explorerFiles, setExplorerFiles] = useState<ExplorerFile[]>([]);
  const [explorerLoading, setExplorerLoading] = useState(false);
  const [explorerError, setExplorerError] = useState<string | null>(null);
  const [selectedFileName, setSelectedFileName] = useState('');
  const [selectedIsDirectory, setSelectedIsDirectory] = useState(false);
  const [formData, setFormData] = useState<CreateFileShareRequest>({
    file_id: fileId || 0,
    shared_with_user_id: 0,
    can_read: true,
    can_write: false,
    can_delete: false,
    can_share: false,
    expires_at: null,
  });

  const fetchFiles = useCallback(async (path: string) => {
    setExplorerLoading(true);
    setExplorerError(null);
    try {
      const response = await apiClient.get('/api/files/list', { params: { path: path || '/' } });
      setExplorerFiles(response.data.files || []);
    } catch {
      setExplorerFiles([]);
      setExplorerError('Failed to load files');
    } finally {
      setExplorerLoading(false);
    }
  }, []);

  // Load files for explorer when no fileId is pre-set
  useEffect(() => {
    if (!fileId) {
      fetchFiles(explorerPath);
    }
  }, [explorerPath, fileId, fetchFiles]);

  const navigateTo = (path: string) => {
    setExplorerPath(path);
  };

  const goUp = () => {
    const parts = explorerPath.split('/').filter(Boolean);
    parts.pop();
    navigateTo(parts.join('/'));
  };

  const selectFile = (file: ExplorerFile) => {
    if (file.file_id) {
      setFormData(prev => ({ ...prev, file_id: file.file_id! }));
      setSelectedFileName(file.name);
      setSelectedIsDirectory(file.type === 'directory');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
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

  const breadcrumbs = explorerPath.split('/').filter(Boolean);

  // Sort: directories first, then files, alphabetical within each group
  const sortedFiles = [...explorerFiles].sort((a, b) => {
    const aIsDir = a.type === 'directory' ? 0 : 1;
    const bIsDir = b.type === 'directory' ? 0 : 1;
    if (aIsDir !== bIsDir) return aIsDir - bIsDir;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto shadow-2xl">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-white">{t('shares:modal.shareWithUser')}</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* File Explorer Selection */}
          {!fileId && (
            <div>
              <label className="block text-sm font-medium mb-2 text-white">
                {t('shares:form.selectItemToShare')}
              </label>

              {/* Breadcrumb bar */}
              <div className="flex items-center gap-1 rounded-t-lg border border-b-0 border-slate-700/50 bg-slate-800/40 px-3 py-2 text-sm">
                {explorerPath !== '' && (
                  <button
                    type="button"
                    onClick={goUp}
                    className="mr-1 rounded p-1 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200"
                  >
                    <ArrowLeft className="h-4 w-4" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => navigateTo('')}
                  className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-700/50 hover:text-sky-400"
                >
                  Home
                </button>
                {breadcrumbs.map((part, i) => (
                  <span key={i} className="flex items-center gap-1">
                    <ChevronRight className="h-3 w-3 text-slate-600" />
                    <button
                      type="button"
                      onClick={() => navigateTo(breadcrumbs.slice(0, i + 1).join('/'))}
                      className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-700/50 hover:text-sky-400 truncate max-w-[120px]"
                    >
                      {part}
                    </button>
                  </span>
                ))}
              </div>

              {/* File list */}
              <div className="max-h-[240px] min-h-[120px] overflow-y-auto rounded-b-lg border border-slate-700/50 bg-slate-800/20">
                {explorerLoading ? (
                  <div className="flex items-center justify-center gap-2 py-10 text-slate-500">
                    <Loader2 className="h-5 w-5 animate-spin" />
                    <span>Loading...</span>
                  </div>
                ) : explorerError ? (
                  <div className="flex items-center justify-center gap-2 py-10 text-red-400">
                    <AlertCircle className="h-5 w-5" />
                    <span>{explorerError}</span>
                  </div>
                ) : sortedFiles.length === 0 ? (
                  <div className="py-10 text-center text-slate-500 text-sm">
                    No files in this directory
                  </div>
                ) : (
                  <div className="divide-y divide-slate-700/20">
                    {sortedFiles.map((file) => {
                      const isDir = file.type === 'directory';
                      const isSelected = file.file_id === formData.file_id && formData.file_id !== 0;

                      return (
                        <div
                          key={file.path}
                          className={`flex items-center gap-3 px-4 py-2.5 transition-colors cursor-pointer ${
                            isSelected
                              ? 'bg-sky-500/10 border-l-2 border-l-sky-500'
                              : 'border-l-2 border-l-transparent hover:bg-slate-700/30'
                          }`}
                          onClick={() => {
                            if (isDir) {
                              navigateTo(file.path);
                            } else {
                              selectFile(file);
                            }
                          }}
                        >
                          {isDir ? (
                            <Folder className="h-4 w-4 shrink-0 text-amber-400" />
                          ) : (
                            <FileIcon className="h-4 w-4 shrink-0 text-slate-400" />
                          )}
                          <span className="min-w-0 flex-1 truncate text-sm text-slate-200">
                            {file.name}
                          </span>
                          {isDir ? (
                            <>
                              {file.file_id && (
                                <button
                                  type="button"
                                  onClick={(e) => { e.stopPropagation(); selectFile(file); }}
                                  className={`p-1 rounded transition-colors ${
                                    isSelected ? 'text-sky-400 bg-sky-500/20' : 'text-slate-500 hover:text-sky-400 hover:bg-sky-500/10'
                                  }`}
                                  title={t('shares:form.selectFolder')}
                                >
                                  <Check className="h-3.5 w-3.5" />
                                </button>
                              )}
                              <ChevronRight className="h-4 w-4 shrink-0 text-slate-600" />
                            </>
                          ) : (
                            <>
                              {file.size != null && (
                                <span className="text-xs text-slate-500 shrink-0">
                                  {formatBytes(file.size)}
                                </span>
                              )}
                              {isSelected && (
                                <Check className="h-4 w-4 shrink-0 text-sky-400" />
                              )}
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Selected file display */}
              {selectedFileName && formData.file_id !== 0 && (
                <p className="mt-1.5 truncate text-xs text-slate-400">
                  {t('shares:form.selected')}: <span className="text-sky-400">{selectedFileName}</span>
                  {selectedIsDirectory && (
                    <span className="text-amber-400 ml-1">({t('shares:form.folder')})</span>
                  )}
                </p>
              )}
              {formData.file_id === 0 && (
                <div className="text-xs text-red-400 mt-1.5">
                  {t('shares:form.selectItemRequired')}
                </div>
              )}
            </div>
          )}

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
              disabled={loading || formData.file_id === 0 || formData.shared_with_user_id === 0}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 touch-manipulation active:scale-95 transition-all"
            >
              {loading ? t('shares:buttons.sharing') : t('shares:buttons.share')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CreateFileShareModal;
