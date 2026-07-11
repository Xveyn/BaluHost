// client/src/pages/SharesPage.tsx
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Loader2 } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { deleteFileShare, getShareableUsers, type FileShare } from '../api/shares';
import { useFileShares } from '../hooks/useFileShares';
import { useCloudExports } from '../hooks/useCloudExports';
import { useSortableTable } from '../hooks/useSortableTable';
import { useConfirmDialog } from '../hooks/useConfirmDialog';
import { queryKeys } from '../lib/queryKeys';
import CreateFileShareModal from '../components/CreateFileShareModal';
import EditFileShareModal from '../components/EditFileShareModal';
import {
  SharesStatCards,
  SharesTabBar,
  SharesToolbar,
  MySharesTable,
  SharedWithMeTable,
  CloudExportsTable,
  getProviderLabel,
  type SharesTab,
} from '../components/shares';

type StatusFilter = 'all' | 'active' | 'expired';

export default function SharesPage() {
  const { t } = useTranslation(['shares', 'common']);
  const { confirm, dialog } = useConfirmDialog();
  const queryClient = useQueryClient();

  const [users, setUsers] = useState<Array<{ id: number; username: string; role: string }>>([]);
  const [activeTab, setActiveTab] = useState<SharesTab>('shares');
  const [showCreateShareModal, setShowCreateShareModal] = useState(false);
  const [editingShare, setEditingShare] = useState<FileShare | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [showFilters, setShowFilters] = useState(false);

  const { fileShares, sharedWithMe, statistics, loading: sharesLoading } = useFileShares();
  const { cloudExports, cloudStats, loading: cloudLoading, revoke, retry } = useCloudExports();
  const loading = sharesLoading || cloudLoading;

  useEffect(() => {
    getShareableUsers()
      .then((data) => setUsers(Array.isArray(data) ? data.map((u) => ({ id: u.id, username: u.username, role: '' })) : []))
      .catch(() => setUsers([]));
  }, []);

  const deleteShareMutation = useMutation({
    mutationFn: (shareId: number) => deleteFileShare(shareId),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: queryKeys.shares.all() }); },
    onError: () => { toast.error(t('shares:toast.revokeFailed')); },
  });

  const handleDeleteFileShare = async (shareId: number) => {
    const ok = await confirm(t('confirm.revokeShare'), { title: t('confirm.revokeShare'), variant: 'danger', confirmLabel: t('common:actions.revoke', 'Revoke') });
    if (!ok) return;
    deleteShareMutation.mutate(shareId);
  };

  const handleCopyLink = (link: string) => {
    navigator.clipboard.writeText(link);
    toast.success(t('shares:cloudExport.linkCopied', 'Link copied'));
  };

  const handleRevokeExport = async (jobId: number) => {
    const ok = await confirm(t('shares:cloudExport.revokeConfirm', 'Revoke this cloud share?'), {
      title: t('shares:cloudExport.revoke', 'Revoke'), variant: 'danger', confirmLabel: t('shares:cloudExport.revoke', 'Revoke'),
    });
    if (!ok) return;
    await revoke(jobId);
  };

  const matchesFilters = (isExpired: boolean, ...fields: Array<string | null | undefined>) => {
    if (statusFilter === 'active' && isExpired) return false;
    if (statusFilter === 'expired' && !isExpired) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return fields.some((f) => f?.toLowerCase().includes(q));
    }
    return true;
  };

  const filteredFileShares = Array.isArray(fileShares)
    ? fileShares.filter((s) => matchesFilters(s.is_expired, s.file_name, s.shared_with_username))
    : [];
  const filteredSharedWithMe = Array.isArray(sharedWithMe)
    ? sharedWithMe.filter((i) => matchesFilters(i.is_expired, i.file_name, i.owner_username))
    : [];

  const shares = useSortableTable(filteredFileShares);
  const shared = useSortableTable(filteredSharedWithMe);
  const cloud = useSortableTable(cloudExports, { getValueForSort: { provider: (job) => getProviderLabel(job) } });

  return (
    <div className="space-y-6 min-w-0">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">{t('description')}</p>
        </div>
      </div>

      <SharesStatCards activeTab={activeTab} statistics={statistics} cloudStats={cloudStats} />
      <SharesTabBar activeTab={activeTab} onChange={setActiveTab} />
      <SharesToolbar
        searchQuery={searchQuery}
        onSearch={setSearchQuery}
        statusFilter={statusFilter}
        onStatusFilter={setStatusFilter}
        showFilters={showFilters}
        onToggleFilters={() => setShowFilters((v) => !v)}
        showCreateButton={activeTab === 'shares'}
        onCreate={() => setShowCreateShareModal(true)}
      />

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
              {activeTab === 'shares' && (
                <MySharesTable
                  shares={shares.sortedData}
                  allCount={fileShares.length}
                  sortKey={shares.sortKey}
                  sortDirection={shares.sortDirection}
                  onSort={shares.toggleSort}
                  onEdit={setEditingShare}
                  onDelete={handleDeleteFileShare}
                />
              )}
              {activeTab === 'shared-with-me' && (
                <SharedWithMeTable
                  items={shared.sortedData}
                  allCount={sharedWithMe.length}
                  sortKey={shared.sortKey}
                  sortDirection={shared.sortDirection}
                  onSort={shared.toggleSort}
                />
              )}
              {activeTab === 'cloud-exports' && (
                <CloudExportsTable
                  jobs={cloud.sortedData}
                  sortKey={cloud.sortKey}
                  sortDirection={cloud.sortDirection}
                  onSort={cloud.toggleSort}
                  onCopyLink={handleCopyLink}
                  onRevoke={handleRevokeExport}
                  onRetry={retry}
                />
              )}
            </>
          )}
        </div>
      </div>

      {/* Modals */}
      {showCreateShareModal && (
        <CreateFileShareModal users={users} onClose={() => setShowCreateShareModal(false)} onSuccess={() => setShowCreateShareModal(false)} />
      )}
      {editingShare && (
        <EditFileShareModal fileShare={editingShare} onClose={() => setEditingShare(null)} onSuccess={() => setEditingShare(null)} />
      )}
      {dialog}
    </div>
  );
}
