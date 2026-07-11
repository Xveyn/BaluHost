/**
 * useVclSettings
 * Data/state hook for VCL Settings (Admin) — owns all state, the mount
 * effect, and every handler used by VCLSettings.tsx.
 */

import { useState, useEffect } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { useTranslation } from 'react-i18next';
import { getApiErrorMessage } from '../lib/errorHandling';
import {
  getAdminOverview,
  getAdminUsers,
  getStorageInfo,
  updateUserSettingsAdmin,
  triggerCleanup,
  getReconciliationPreview,
  applyReconciliation,
  formatBytes,
} from '../api/vcl';
import type {
  AdminVCLOverview,
  UserVCLStats,
  VCLSettingsUpdate,
  VCLStorageInfo,
  ReconciliationPreview,
} from '../types/vcl';

export interface UseVclSettingsResult {
  overview: AdminVCLOverview | null;
  storageInfo: VCLStorageInfo | null;
  users: UserVCLStats[];
  loading: boolean;
  actionLoading: boolean;
  error: string | null;
  successMessage: string | null;
  editingUser: UserVCLStats | null;
  editForm: VCLSettingsUpdate;
  setEditForm: Dispatch<SetStateAction<VCLSettingsUpdate>>;
  reconPreview: ReconciliationPreview | null;
  reconLoading: boolean;
  forceOverQuota: boolean;
  setForceOverQuota: Dispatch<SetStateAction<boolean>>;
  loadData: () => Promise<void>;
  handleCleanup: (dryRun?: boolean) => Promise<void>;
  handleScanMismatches: () => Promise<void>;
  handleApplyReconciliation: () => Promise<void>;
  handleEditUser: (user: UserVCLStats) => void;
  handleSaveUserSettings: () => Promise<void>;
  setEditingUser: Dispatch<SetStateAction<UserVCLStats | null>>;
}

export function useVclSettings(): UseVclSettingsResult {
  const [overview, setOverview] = useState<AdminVCLOverview | null>(null);
  const [storageInfo, setStorageInfo] = useState<VCLStorageInfo | null>(null);
  const [users, setUsers] = useState<UserVCLStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Edit modal state
  const [editingUser, setEditingUser] = useState<UserVCLStats | null>(null);
  const [editForm, setEditForm] = useState<VCLSettingsUpdate>({});
  const { t } = useTranslation('admin');

  // Reconciliation state
  const [reconPreview, setReconPreview] = useState<ReconciliationPreview | null>(null);
  const [reconLoading, setReconLoading] = useState(false);
  const [forceOverQuota, setForceOverQuota] = useState(false);

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [overviewData, usersData, storageData] = await Promise.all([
        getAdminOverview(),
        getAdminUsers(100, 0),
        getStorageInfo().catch(() => null),
      ]);
      setOverview(overviewData);
      setUsers(usersData?.users || []);
      setStorageInfo(storageData);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, t('vcl.errors.loadFailed')));
      // Set empty arrays on error
      setUsers([]);
      setOverview(null);
    } finally {
      setLoading(false);
    }
  };

  const handleCleanup = async (dryRun: boolean = false) => {
    if (!dryRun && !confirm(t('vcl.maintenance.confirmCleanup'))) return;

    try {
      setActionLoading(true);
      setError(null);
      const result = await triggerCleanup({ dry_run: dryRun });
      setSuccessMessage(
        t(dryRun ? 'vcl.cleanup.dryRunResult' : 'vcl.cleanup.result', { versions: result.deleted_versions, freed: formatBytes(result.freed_bytes) })
      );
      setTimeout(() => setSuccessMessage(null), 5000);
      if (!dryRun) loadData(); // Reload stats
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, t('vcl.errors.cleanupFailed')));
    } finally {
      setActionLoading(false);
    }
  };

  const handleScanMismatches = async () => {
    try {
      setReconLoading(true);
      setError(null);
      const preview = await getReconciliationPreview({});
      setReconPreview(preview);
      if (preview.total_mismatches === 0) {
        setSuccessMessage('No ownership mismatches found');
        setTimeout(() => setSuccessMessage(null), 3000);
      }
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Failed to scan for mismatches'));
    } finally {
      setReconLoading(false);
    }
  };

  const handleApplyReconciliation = async () => {
    if (!confirm('Apply ownership reconciliation? This will update version ownership to match file ownership.')) return;
    try {
      setReconLoading(true);
      setError(null);
      const result = await applyReconciliation({ force_over_quota: forceOverQuota });
      setSuccessMessage(result.message);
      setTimeout(() => setSuccessMessage(null), 5000);
      setReconPreview(null);
      loadData();
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Failed to apply reconciliation'));
    } finally {
      setReconLoading(false);
    }
  };

  const handleEditUser = (user: UserVCLStats) => {
    setEditingUser(user);
    setEditForm({
      max_size_bytes: user.max_size_bytes,
      is_enabled: user.is_enabled,
    });
  };

  const handleSaveUserSettings = async () => {
    if (!editingUser) return;

    try {
      setActionLoading(true);
      setError(null);
      await updateUserSettingsAdmin(editingUser.user_id, editForm);
      setSuccessMessage(t('vcl.settingsUpdated', { username: editingUser.username }));
      setTimeout(() => setSuccessMessage(null), 3000);
      setEditingUser(null);
      loadData(); // Reload
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, t('vcl.errors.updateFailed')));
    } finally {
      setActionLoading(false);
    }
  };

  return {
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
  };
}
