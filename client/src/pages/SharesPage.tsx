import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import {
  listFileShares,
  listFilesSharedWithMe,
  getShareStatistics,
  getShareableUsers,
  deleteFileShare,
  type FileShare,
  type SharedWithMe,
  type ShareStatistics
} from '../api/shares';
import { Users, Share2, Trash2, Edit, Search, Filter, Calendar, Loader2, Folder, File as FileIcon, Cloud, Copy, RefreshCw } from 'lucide-react';
import {
  listCloudExports,
  getCloudExportStatistics,
  revokeCloudExport,
  retryCloudExport,
  type CloudExportJob,
  type CloudExportStatistics as CloudExportStats,
} from '../api/cloud-export';
import { formatBytes } from '../lib/formatters';
import { StatCard } from '../components/ui/StatCard';
import CreateFileShareModal from '../components/CreateFileShareModal';
import EditFileShareModal from '../components/EditFileShareModal';
import { useConfirmDialog } from '../hooks/useConfirmDialog';

export default function SharesPage() {
  const { t } = useTranslation(['shares', 'common']);
  const { confirm, dialog } = useConfirmDialog();
  // User list for modal
  const [users, setUsers] = useState<Array<{ id: number; username: string; role: string }>>([]);
  const [activeTab, setActiveTab] = useState<'shares' | 'shared-with-me' | 'cloud-exports'>('shares');
  const [cloudExports, setCloudExports] = useState<CloudExportJob[]>([]);
  const [cloudStats, setCloudStats] = useState<CloudExportStats | null>(null);
  const [fileShares, setFileShares] = useState<FileShare[]>([]);
  const [sharedWithMe, setSharedWithMe] = useState<SharedWithMe[]>([]);
  const [statistics, setStatistics] = useState<ShareStatistics | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCreateShareModal, setShowCreateShareModal] = useState(false);

  // Edit modals
  const [editingShare, setEditingShare] = useState<FileShare | null>(null);

  // Filter and search
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'expired'>('all');
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    loadData();
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      const data = await getShareableUsers();
      setUsers(Array.isArray(data) ? data.map(u => ({ id: u.id, username: u.username, role: '' })) : []);
    } catch {
      setUsers([]);
    }
  };

  const loadData = async () => {
    setLoading(true);
    try {
      const [stats, shares, shared, cExports, cStats] = await Promise.all([
        getShareStatistics(),
        listFileShares(),
        listFilesSharedWithMe(),
        listCloudExports().catch(() => []),
        getCloudExportStatistics().catch(() => null),
      ]);
      setStatistics(stats);
      setFileShares(shares);
      setSharedWithMe(shared);
      setCloudExports(cExports);
      setCloudStats(cStats);
    } catch {
      // Load failure handled by empty state
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteFileShare = async (shareId: number) => {
    const ok = await confirm(t('confirm.revokeShare'), { title: t('confirm.revokeShare'), variant: 'danger', confirmLabel: t('common:actions.revoke', 'Revoke') });
    if (!ok) return;

    try {
      await deleteFileShare(shareId);
      await loadData();
    } catch {
      toast.error(t('shares:toast.revokeFailed'));
    }
  };

  const handleCopyLink = (link: string) => {
    navigator.clipboard.writeText(link);
    toast.success(t('shares:cloudExport.linkCopied', 'Link copied'));
  };

  const handleRevokeExport = async (jobId: number) => {
    const ok = await confirm(t('shares:cloudExport.revokeConfirm', 'Revoke this cloud share?'), {
      title: t('shares:cloudExport.revoke', 'Revoke'),
      variant: 'danger',
      confirmLabel: t('shares:cloudExport.revoke', 'Revoke'),
    });
    if (!ok) return;
    try {
      await revokeCloudExport(jobId);
      await loadData();
      toast.success(t('shares:cloudExport.revoked', 'Cloud share revoked'));
    } catch {
      toast.error(t('shares:cloudExport.revokeFailed', 'Failed to revoke cloud share'));
    }
  };

  const handleRetryExport = async (jobId: number) => {
    try {
      await retryCloudExport(jobId);
      await loadData();
      toast.success(t('shares:cloudExport.retryStarted', 'Retry started'));
    } catch {
      toast.error(t('shares:cloudExport.retryFailed', 'Retry failed'));
    }
  };

  const getProviderLabel = (job: CloudExportJob) => {
    if (job.share_link?.includes('drive.google')) return 'Google Drive';
    if (job.share_link?.includes('1drv.ms') || job.share_link?.includes('sharepoint')) return 'OneDrive';
    return 'Cloud';
  };

  const getStatusBadge = (job: CloudExportJob) => {
    switch (job.status) {
      case 'ready':
        return <span className="px-2.5 py-1 bg-green-500/20 text-green-400 rounded-full text-xs font-semibold">{t('shares:cloudExport.statusReady', 'Ready')}</span>;
      case 'uploading':
      case 'creating_link':
        return (
          <span className="px-2.5 py-1 bg-blue-500/20 text-blue-400 rounded-full text-xs font-semibold inline-flex items-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin" />
            {job.status === 'uploading'
              ? (job.file_size_bytes
                ? `${Math.round((job.progress_bytes / job.file_size_bytes) * 100)}%`
                : t('shares:cloudExport.statusUploading', 'Uploading'))
              : t('shares:cloudExport.statusCreatingLink', 'Creating link')}
          </span>
        );
      case 'pending':
        return <span className="px-2.5 py-1 bg-slate-500/20 text-slate-400 rounded-full text-xs font-semibold">{t('shares:cloudExport.statusPending', 'Pending')}</span>;
      case 'failed':
        return <span className="px-2.5 py-1 bg-red-500/20 text-red-400 rounded-full text-xs font-semibold">{t('shares:cloudExport.statusFailed', 'Failed')}</span>;
      case 'revoked':
        return <span className="px-2.5 py-1 bg-slate-500/20 text-slate-500 rounded-full text-xs font-semibold">{t('shares:cloudExport.statusRevoked', 'Revoked')}</span>;
      default:
        return <span className="px-2.5 py-1 bg-slate-500/20 text-slate-400 rounded-full text-xs font-semibold">{job.status}</span>;
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return t('common:time.never');
    return new Date(dateString).toLocaleDateString();
  };

  const formatFileSize = (bytes: number | null) => {
    if (!bytes) return '0 B';
    return formatBytes(bytes);
  };

  const filteredFileShares = Array.isArray(fileShares) ? fileShares.filter(share => {
    // Status filter
    if (statusFilter === 'active' && share.is_expired) return false;
    if (statusFilter === 'expired' && !share.is_expired) return false;

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        share.file_name?.toLowerCase().includes(query) ||
        share.shared_with_username?.toLowerCase().includes(query)
      );
    }

    return true;
  }) : [];

  const filteredSharedWithMe = Array.isArray(sharedWithMe) ? sharedWithMe.filter(item => {
    // Status filter
    if (statusFilter === 'active' && item.is_expired) return false;
    if (statusFilter === 'expired' && !item.is_expired) return false;

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        item.file_name.toLowerCase().includes(query) ||
        item.owner_username.toLowerCase().includes(query)
      );
    }

    return true;
  }) : [];

  const tabs = [
    { key: 'shares' as const, label: t('tabs.userShares'), shortLabel: t('tabs.shares'), icon: Users },
    { key: 'shared-with-me' as const, label: t('tabs.sharedWithMe'), shortLabel: t('tabs.received'), icon: Share2 },
    { key: 'cloud-exports' as const, label: t('tabs.cloudExports', 'Cloud Shares'), shortLabel: t('tabs.cloudExportsShort', 'Cloud'), icon: Cloud },
  ];

  return (
    <div className="space-y-6 min-w-0">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">{t('description')}</p>
        </div>
      </div>

      {/* Statistics Cards */}
      {activeTab !== 'cloud-exports' && statistics && (
        <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-5">
          <StatCard
            label={t('stats.userShares')}
            value={statistics.active_file_shares}
            subValue={t('stats.ofTotal', { total: statistics.total_file_shares })}
            color="purple"
            icon={<Users className="h-5 w-5 sm:h-6 sm:w-6 text-purple-400" />}
          />
          <StatCard
            label={t('stats.sharedWithMe')}
            value={statistics.files_shared_with_me}
            subValue={t('stats.filesAccessible')}
            color="amber"
            icon={<Share2 className="h-5 w-5 sm:h-6 sm:w-6 text-amber-400" />}
          />
        </div>
      )}
      {activeTab === 'cloud-exports' && cloudStats && (
        <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-5">
          <StatCard
            label={t('shares:cloudExport.activeShares', 'Active Cloud Shares')}
            value={cloudStats.active_exports}
            subValue={t('stats.ofTotal', { total: cloudStats.total_exports })}
            color="blue"
            icon={<Cloud className="h-5 w-5 sm:h-6 sm:w-6 text-blue-400" />}
          />
          <StatCard
            label={t('shares:cloudExport.uploadVolume', 'Upload Volume')}
            value={formatBytes(cloudStats.total_upload_bytes)}
            subValue={t('shares:cloudExport.totalUploaded', 'Total uploaded')}
            color="green"
            icon={<Cloud className="h-5 w-5 sm:h-6 sm:w-6 text-green-400" />}
          />
        </div>
      )}

      {/* Tab Bar */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
        <div className="flex gap-2 border-b border-slate-800 pb-3 min-w-max sm:min-w-0">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-3 sm:px-4 py-2 rounded-lg text-sm font-medium transition-all touch-manipulation active:scale-95 ${
                activeTab === tab.key
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                  : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              <span className="hidden sm:inline">{tab.label}</span>
              <span className="sm:hidden">{tab.shortLabel}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Search and Filter Bar */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
          {/* Search */}
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 sm:w-5 sm:h-5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('search.placeholder')}
              className="w-full pl-10 sm:pl-11 pr-4 py-2.5 sm:py-3 border border-slate-700 bg-slate-900/70 rounded-xl focus:ring-2 focus:ring-sky-500 focus:border-sky-500 transition-all text-slate-200 placeholder-slate-500 text-sm sm:text-base"
            />
          </div>

          {/* Filter Toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`px-4 sm:px-5 py-2.5 sm:py-3 border rounded-xl flex items-center justify-center gap-2 font-medium transition-all touch-manipulation active:scale-95 text-sm sm:text-base ${
              showFilters ? 'bg-blue-500/20 border-blue-500/40 text-blue-400' : 'border-slate-700 text-slate-300 hover:bg-slate-800/50'
            }`}
          >
            <Filter className="w-4 h-4 sm:w-5 sm:h-5" />
            <span>{t('search.filters')}</span>
          </button>

          {/* Action Button — only in My Shares tab */}
          {activeTab === 'shares' && (
            <button
              onClick={() => setShowCreateShareModal(true)}
              className="btn btn-primary flex items-center justify-center gap-2 touch-manipulation active:scale-95"
            >
              <Users className="w-4 h-4 sm:w-5 sm:h-5" />
              <span className="hidden sm:inline">{t('buttons.shareWithUser')}</span>
              <span className="sm:hidden">{t('buttons.share')}</span>
            </button>
          )}
        </div>

        {/* Filter Options */}
        {showFilters && (
          <div className="flex flex-wrap gap-2 sm:gap-3 p-3 sm:p-4 bg-slate-800/30 rounded-xl border border-slate-700/50">
            <span className="text-xs sm:text-sm font-semibold text-slate-300 flex items-center mr-2">
              {t('search.status')}:
            </span>
            {(['all', 'active', 'expired'] as const).map((status) => (
              <label key={status} className="flex items-center cursor-pointer">
                <input
                  type="radio"
                  value={status}
                  checked={statusFilter === status}
                  onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
                  className="mr-1.5 sm:mr-2 w-4 h-4 text-sky-500"
                />
                <span className="text-xs sm:text-sm font-medium text-slate-300 capitalize">{t(`search.${status}`)}</span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="card border-slate-800/60 bg-slate-900/55 overflow-hidden">
        <div className="p-4 sm:p-6">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12 sm:py-16">
              <Loader2 className="h-8 w-8 animate-spin text-blue-500 mb-4" />
              <p className="text-slate-400 font-medium text-sm sm:text-base">{t('loading')}</p>
            </div>
          ) : (
            <>
              {/* File Shares Tab */}
              {activeTab === 'shares' && (
                <>
                  {filteredFileShares.length === 0 ? (
                    <div className="text-center py-8 sm:py-12">
                      <Users className="w-12 h-12 sm:w-16 sm:h-16 text-slate-600 mx-auto mb-4 opacity-50" />
                      <h3 className="text-base sm:text-lg font-semibold text-slate-300 mb-2">
                        {fileShares.length === 0 ? t('empty.noShares') : t('empty.noMatchingShares')}
                      </h3>
                      <p className="text-slate-500 text-sm sm:text-base">
                        {fileShares.length === 0
                          ? t('empty.noSharesDesc')
                          : t('empty.tryAdjusting')}
                      </p>
                    </div>
                  ) : (
                    <>
                      {/* Desktop Table */}
                      <div className="hidden lg:block overflow-x-auto">
                        <table className="min-w-full">
                          <thead className="bg-slate-800/30 border-b border-slate-700/50">
                            <tr>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.file')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.owner')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.sharedWith')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.permissions')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.expires')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.actions')}</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60">
                            {filteredFileShares.map((share) => (
                              <tr key={share.id} className="hover:bg-slate-800/30 transition-colors">
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="flex items-center gap-2">
                                    {share.is_directory
                                      ? <Folder className="h-4 w-4 shrink-0 text-amber-400" />
                                      : <FileIcon className="h-4 w-4 shrink-0 text-slate-400" />}
                                    <div>
                                      <div className="font-semibold text-white">{share.file_name}</div>
                                      <div className="text-xs sm:text-sm text-slate-400 mt-0.5">
                                        {share.is_directory ? t('form.folder') : formatFileSize(share.file_size)}
                                      </div>
                                    </div>
                                  </div>
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-slate-300 font-medium">{share.owner_username}</td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-slate-300 font-medium">{share.shared_with_username}</td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="flex space-x-1">
                                    {share.can_read && (
                                      <span className="px-2.5 py-1 border border-sky-500/40 bg-sky-500/15 text-sky-300 rounded-full text-xs font-semibold">
                                        {t('permissions.read')}
                                      </span>
                                    )}
                                    {share.can_write && (
                                      <span className="px-2.5 py-1 border border-green-500/40 bg-green-500/15 text-green-300 rounded-full text-xs font-semibold">
                                        {t('permissions.write')}
                                      </span>
                                    )}
                                    {share.can_delete && (
                                      <span className="px-2.5 py-1 border border-rose-500/40 bg-rose-500/15 text-rose-300 rounded-full text-xs font-semibold">
                                        {t('permissions.delete')}
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">
                                  {formatDate(share.expires_at)}
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="flex space-x-1">
                                    <button
                                      onClick={() => setEditingShare(share)}
                                      className="p-2 rounded-lg border border-green-500/30 bg-green-500/10 text-green-200 transition hover:border-green-500/50 hover:bg-green-500/20"
                                      title={t('buttons.edit')}
                                    >
                                      <Edit className="w-4 h-4 sm:w-5 sm:h-5" />
                                    </button>
                                    <button
                                      onClick={() => handleDeleteFileShare(share.id)}
                                      className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
                                      title={t('buttons.revoke')}
                                    >
                                      <Trash2 className="w-4 h-4 sm:w-5 sm:h-5" />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Mobile Card View */}
                      <div className="lg:hidden space-y-3">
                        {filteredFileShares.map((share) => (
                          <div
                            key={share.id}
                            className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4"
                          >
                            <div className="flex items-start justify-between gap-2 mb-3">
                              <div className="min-w-0 flex-1 flex items-center gap-2">
                                {share.is_directory
                                  ? <Folder className="h-4 w-4 shrink-0 text-amber-400" />
                                  : <FileIcon className="h-4 w-4 shrink-0 text-slate-400" />}
                                <div className="min-w-0">
                                  <p className="font-semibold text-white truncate">{share.file_name}</p>
                                  <p className="text-xs text-slate-400">{share.is_directory ? t('form.folder') : formatFileSize(share.file_size)}</p>
                                </div>
                              </div>
                              <div className="flex gap-1 flex-shrink-0">
                                <button
                                  onClick={() => setEditingShare(share)}
                                  className="p-2 rounded-lg border border-green-500/30 bg-green-500/10 text-green-200 transition touch-manipulation active:scale-95"
                                  title={t('buttons.edit')}
                                >
                                  <Edit className="w-4 h-4" />
                                </button>
                                <button
                                  onClick={() => handleDeleteFileShare(share.id)}
                                  className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition touch-manipulation active:scale-95"
                                  title={t('buttons.revoke')}
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </div>
                            </div>

                            <div className="flex items-center gap-2 mb-2">
                              <Users className="h-3 w-3 text-slate-400" />
                              <span className="text-sm text-slate-300">{t('table.owner')}: {share.owner_username}</span>
                            </div>

                            <div className="flex items-center gap-2 mb-2">
                              <Users className="h-3 w-3 text-slate-400" />
                              <span className="text-sm text-slate-300">{share.shared_with_username}</span>
                            </div>

                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              {share.can_read && (
                                <span className="px-2 py-0.5 border border-sky-500/40 bg-sky-500/15 text-sky-300 rounded-full text-xs font-semibold">
                                  {t('permissions.read')}
                                </span>
                              )}
                              {share.can_write && (
                                <span className="px-2 py-0.5 border border-green-500/40 bg-green-500/15 text-green-300 rounded-full text-xs font-semibold">
                                  {t('permissions.write')}
                                </span>
                              )}
                              {share.can_delete && (
                                <span className="px-2 py-0.5 border border-rose-500/40 bg-rose-500/15 text-rose-300 rounded-full text-xs font-semibold">
                                  {t('permissions.delete')}
                                </span>
                              )}
                            </div>

                            <div className="text-xs text-slate-400 flex items-center gap-1">
                              <Calendar className="h-3 w-3" />
                              {t('table.expires')}: {formatDate(share.expires_at)}
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </>
              )}

              {/* Shared With Me Tab */}
              {activeTab === 'shared-with-me' && (
                <>
                  {filteredSharedWithMe.length === 0 ? (
                    <div className="text-center py-8 sm:py-12">
                      <Share2 className="w-12 h-12 sm:w-16 sm:h-16 text-slate-600 mx-auto mb-4 opacity-50" />
                      <h3 className="text-base sm:text-lg font-semibold text-slate-300 mb-2">
                        {sharedWithMe.length === 0 ? t('empty.noFilesShared') : t('empty.noMatchingFilesShared')}
                      </h3>
                      <p className="text-slate-500 text-sm sm:text-base">
                        {sharedWithMe.length === 0
                          ? t('empty.noFilesSharedDesc')
                          : t('empty.tryAdjusting')}
                      </p>
                    </div>
                  ) : (
                    <>
                      {/* Desktop Table */}
                      <div className="hidden lg:block overflow-x-auto">
                        <table className="min-w-full">
                          <thead className="bg-slate-800/30 border-b border-slate-700/50">
                            <tr>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.file')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.owner')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.permissions')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.shared')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.expires')}</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60">
                            {filteredSharedWithMe.map((item) => (
                              <tr key={item.share_id} className="hover:bg-slate-800/30 transition-colors">
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="flex items-center gap-2">
                                    {item.is_directory
                                      ? <Folder className="h-4 w-4 shrink-0 text-amber-400" />
                                      : <FileIcon className="h-4 w-4 shrink-0 text-slate-400" />}
                                    <div>
                                      <div className="font-semibold text-white">{item.file_name}</div>
                                      <div className="text-xs sm:text-sm text-slate-400 mt-0.5">
                                        {item.is_directory ? t('form.folder') : formatFileSize(item.file_size)}
                                      </div>
                                    </div>
                                  </div>
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-slate-300 font-medium">{item.owner_username}</td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="flex space-x-1">
                                    {item.can_read && (
                                      <span className="px-2.5 py-1 border border-sky-500/40 bg-sky-500/15 text-sky-300 rounded-full text-xs font-semibold">
                                        {t('permissions.read')}
                                      </span>
                                    )}
                                    {item.can_write && (
                                      <span className="px-2.5 py-1 border border-green-500/40 bg-green-500/15 text-green-300 rounded-full text-xs font-semibold">
                                        {t('permissions.write')}
                                      </span>
                                    )}
                                    {item.can_delete && (
                                      <span className="px-2.5 py-1 border border-rose-500/40 bg-rose-500/15 text-rose-300 rounded-full text-xs font-semibold">
                                        {t('permissions.delete')}
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">
                                  {formatDate(item.shared_at)}
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">
                                  {formatDate(item.expires_at)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Mobile Card View */}
                      <div className="lg:hidden space-y-3">
                        {filteredSharedWithMe.map((item) => (
                          <div
                            key={item.share_id}
                            className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4"
                          >
                            <div className="mb-2 flex items-center gap-2">
                              {item.is_directory
                                ? <Folder className="h-4 w-4 shrink-0 text-amber-400" />
                                : <FileIcon className="h-4 w-4 shrink-0 text-slate-400" />}
                              <div className="min-w-0">
                                <p className="font-semibold text-white truncate">{item.file_name}</p>
                                <p className="text-xs text-slate-400">{item.is_directory ? t('form.folder') : formatFileSize(item.file_size)}</p>
                              </div>
                            </div>

                            <div className="flex items-center gap-2 mb-2">
                              <Users className="h-3 w-3 text-slate-400" />
                              <span className="text-sm text-slate-300">{t('table.from')}: {item.owner_username}</span>
                            </div>

                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              {item.can_read && (
                                <span className="px-2 py-0.5 border border-sky-500/40 bg-sky-500/15 text-sky-300 rounded-full text-xs font-semibold">
                                  {t('permissions.read')}
                                </span>
                              )}
                              {item.can_write && (
                                <span className="px-2 py-0.5 border border-green-500/40 bg-green-500/15 text-green-300 rounded-full text-xs font-semibold">
                                  {t('permissions.write')}
                                </span>
                              )}
                              {item.can_delete && (
                                <span className="px-2 py-0.5 border border-rose-500/40 bg-rose-500/15 text-rose-300 rounded-full text-xs font-semibold">
                                  {t('permissions.delete')}
                                </span>
                              )}
                            </div>

                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
                              <span className="flex items-center gap-1">
                                <Calendar className="h-3 w-3" />
                                {t('table.shared')}: {formatDate(item.shared_at)}
                              </span>
                              <span className="flex items-center gap-1">
                                <Calendar className="h-3 w-3" />
                                {t('table.expires')}: {formatDate(item.expires_at)}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </>
              )}

              {/* Cloud Exports Tab */}
              {activeTab === 'cloud-exports' && (
                <>
                  {cloudExports.length === 0 ? (
                    <div className="text-center py-8 sm:py-12">
                      <Cloud className="w-12 h-12 sm:w-16 sm:h-16 text-slate-600 mx-auto mb-4 opacity-50" />
                      <h3 className="text-base sm:text-lg font-semibold text-slate-300 mb-2">
                        {t('shares:cloudExport.noExports', 'No cloud shares')}
                      </h3>
                      <p className="text-slate-500 text-sm sm:text-base">
                        {t('shares:cloudExport.noExportsDesc', 'Share files to cloud storage from the file manager.')}
                      </p>
                    </div>
                  ) : (
                    <>
                      {/* Desktop Table */}
                      <div className="hidden lg:block overflow-x-auto">
                        <table className="min-w-full">
                          <thead className="bg-slate-800/30 border-b border-slate-700/50">
                            <tr>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('shares:cloudExport.provider', 'Provider')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.file')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('shares:cloudExport.link', 'Link')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('search.status', 'Status')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('shares:cloudExport.created', 'Created')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.expires')}</th>
                              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('table.actions')}</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60">
                            {cloudExports.map((job) => (
                              <tr key={job.id} className="hover:bg-slate-800/30 transition-colors">
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <span className="text-slate-300 font-medium">{getProviderLabel(job)}</span>
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="flex items-center gap-2">
                                    {job.is_directory
                                      ? <Folder className="h-4 w-4 shrink-0 text-amber-400" />
                                      : <FileIcon className="h-4 w-4 shrink-0 text-slate-400" />}
                                    <div>
                                      <div className="font-semibold text-white">{job.file_name}</div>
                                      <div className="text-xs sm:text-sm text-slate-400 mt-0.5">
                                        {job.is_directory ? t('form.folder') : formatFileSize(job.file_size_bytes)}
                                      </div>
                                    </div>
                                  </div>
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  {job.share_link ? (
                                    <button
                                      onClick={() => handleCopyLink(job.share_link!)}
                                      className="flex items-center gap-1.5 text-blue-400 hover:text-blue-300 transition-colors text-sm"
                                      title={t('shares:cloudExport.copyLink', 'Copy link')}
                                    >
                                      <Copy className="w-3.5 h-3.5" />
                                      <span className="truncate max-w-[160px]">{t('shares:cloudExport.copyLink', 'Copy link')}</span>
                                    </button>
                                  ) : (
                                    <span className="text-slate-500 text-sm">--</span>
                                  )}
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  {getStatusBadge(job)}
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">
                                  {formatDate(job.created_at)}
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4 text-sm text-slate-300 font-medium">
                                  {formatDate(job.expires_at)}
                                </td>
                                <td className="px-4 sm:px-6 py-3 sm:py-4">
                                  <div className="flex space-x-1">
                                    {job.share_link && (
                                      <button
                                        onClick={() => handleCopyLink(job.share_link!)}
                                        className="p-2 rounded-lg border border-blue-500/30 bg-blue-500/10 text-blue-200 transition hover:border-blue-500/50 hover:bg-blue-500/20"
                                        title={t('shares:cloudExport.copyLink', 'Copy link')}
                                      >
                                        <Copy className="w-4 h-4 sm:w-5 sm:h-5" />
                                      </button>
                                    )}
                                    {job.status === 'ready' && (
                                      <button
                                        onClick={() => handleRevokeExport(job.id)}
                                        className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
                                        title={t('shares:cloudExport.revoke', 'Revoke')}
                                      >
                                        <Trash2 className="w-4 h-4 sm:w-5 sm:h-5" />
                                      </button>
                                    )}
                                    {job.status === 'failed' && (
                                      <button
                                        onClick={() => handleRetryExport(job.id)}
                                        className="p-2 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-200 transition hover:border-amber-500/50 hover:bg-amber-500/20"
                                        title={t('shares:cloudExport.retry', 'Retry')}
                                      >
                                        <RefreshCw className="w-4 h-4 sm:w-5 sm:h-5" />
                                      </button>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Mobile Card View */}
                      <div className="lg:hidden space-y-3">
                        {cloudExports.map((job) => (
                          <div
                            key={job.id}
                            className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4"
                          >
                            <div className="flex items-start justify-between gap-2 mb-3">
                              <div className="min-w-0 flex-1 flex items-center gap-2">
                                {job.is_directory
                                  ? <Folder className="h-4 w-4 shrink-0 text-amber-400" />
                                  : <FileIcon className="h-4 w-4 shrink-0 text-slate-400" />}
                                <div className="min-w-0">
                                  <p className="font-semibold text-white truncate">{job.file_name}</p>
                                  <p className="text-xs text-slate-400">{job.is_directory ? t('form.folder') : formatFileSize(job.file_size_bytes)}</p>
                                </div>
                              </div>
                              <div className="flex gap-1 flex-shrink-0">
                                {job.share_link && (
                                  <button
                                    onClick={() => handleCopyLink(job.share_link!)}
                                    className="p-2 rounded-lg border border-blue-500/30 bg-blue-500/10 text-blue-200 transition touch-manipulation active:scale-95"
                                    title={t('shares:cloudExport.copyLink', 'Copy link')}
                                  >
                                    <Copy className="w-4 h-4" />
                                  </button>
                                )}
                                {job.status === 'ready' && (
                                  <button
                                    onClick={() => handleRevokeExport(job.id)}
                                    className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition touch-manipulation active:scale-95"
                                    title={t('shares:cloudExport.revoke', 'Revoke')}
                                  >
                                    <Trash2 className="w-4 h-4" />
                                  </button>
                                )}
                                {job.status === 'failed' && (
                                  <button
                                    onClick={() => handleRetryExport(job.id)}
                                    className="p-2 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-200 transition touch-manipulation active:scale-95"
                                    title={t('shares:cloudExport.retry', 'Retry')}
                                  >
                                    <RefreshCw className="w-4 h-4" />
                                  </button>
                                )}
                              </div>
                            </div>

                            <div className="flex items-center gap-2 mb-2">
                              <Cloud className="h-3 w-3 text-slate-400" />
                              <span className="text-sm text-slate-300">{getProviderLabel(job)}</span>
                            </div>

                            <div className="flex items-center gap-2 mb-2">
                              {getStatusBadge(job)}
                            </div>

                            {job.share_link && (
                              <button
                                onClick={() => handleCopyLink(job.share_link!)}
                                className="flex items-center gap-1.5 text-blue-400 hover:text-blue-300 transition-colors text-xs mb-2"
                              >
                                <Copy className="w-3 h-3" />
                                {t('shares:cloudExport.copyLink', 'Copy link')}
                              </button>
                            )}

                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
                              <span className="flex items-center gap-1">
                                <Calendar className="h-3 w-3" />
                                {t('shares:cloudExport.created', 'Created')}: {formatDate(job.created_at)}
                              </span>
                              <span className="flex items-center gap-1">
                                <Calendar className="h-3 w-3" />
                                {t('table.expires')}: {formatDate(job.expires_at)}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Modals */}
      {showCreateShareModal && (
        <CreateFileShareModal
          users={users}
          onClose={() => setShowCreateShareModal(false)}
          onSuccess={() => {
            setShowCreateShareModal(false);
            loadData();
          }}
        />
      )}
      {editingShare && (
        <EditFileShareModal
          fileShare={editingShare}
          onClose={() => setEditingShare(null)}
          onSuccess={() => {
            setEditingShare(null);
            loadData();
          }}
        />
      )}
      {dialog}
    </div>
  );
}
