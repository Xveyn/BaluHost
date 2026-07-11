/**
 * VCL Settings Component (Admin)
 * Global VCL settings, per-user limits, stats dashboard, maintenance
 */

import { useVclSettings } from '../../hooks/useVclSettings';
import {
  VclMessageBanners,
  VclStorageInfoCard,
  VclStatsGrid,
  VclStorageDetailsCard,
  VclMaintenanceCard,
  VclReconciliationCard,
  VclUserQuotasTable,
  VclEditUserModal,
} from './vcl-settings';

export default function VCLSettings() {
  const {
    overview,
    storageInfo,
    users,
    loading,
    actionLoading,
    error,
    successMessage,
    editingUser,
    editForm,
    setEditForm,
    reconPreview,
    reconLoading,
    forceOverQuota,
    setForceOverQuota,
    loadData,
    handleCleanup,
    handleScanMismatches,
    handleApplyReconciliation,
    handleEditUser,
    handleSaveUserSettings,
    setEditingUser,
  } = useVclSettings();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500"></div>
      </div>
    );
  }

  if (!overview) return null;

  const compressionRatio = overview.compression_ratio;
  const totalSavings = overview.total_savings_bytes;
  const savingsPercent = overview.total_size_bytes > 0
    ? ((totalSavings / overview.total_size_bytes) * 100)
    : 0;

  return (
    <div className="space-y-6">
      <VclMessageBanners error={error} successMessage={successMessage} />

      {storageInfo && <VclStorageInfoCard storageInfo={storageInfo} />}

      <VclStatsGrid overview={overview} totalSavings={totalSavings} savingsPercent={savingsPercent} />

      <VclStorageDetailsCard overview={overview} compressionRatio={compressionRatio} />

      <VclMaintenanceCard
        actionLoading={actionLoading}
        onDryRunCleanup={() => handleCleanup(true)}
        onTriggerCleanup={() => handleCleanup(false)}
        onRefresh={loadData}
      />

      <VclReconciliationCard
        reconPreview={reconPreview}
        reconLoading={reconLoading}
        forceOverQuota={forceOverQuota}
        onScan={handleScanMismatches}
        onForceChange={setForceOverQuota}
        onApply={handleApplyReconciliation}
      />

      <VclUserQuotasTable users={users} onEditUser={handleEditUser} />

      {editingUser && (
        <VclEditUserModal
          editingUser={editingUser}
          editForm={editForm}
          actionLoading={actionLoading}
          onMaxSizeChange={(bytes) => setEditForm({ ...editForm, max_size_bytes: bytes })}
          onEnabledChange={(v) => setEditForm({ ...editForm, is_enabled: v })}
          onCancel={() => setEditingUser(null)}
          onSave={handleSaveUserSettings}
        />
      )}
    </div>
  );
}
