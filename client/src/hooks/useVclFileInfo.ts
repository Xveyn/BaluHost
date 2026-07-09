import { useCallback, useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { queryKeys } from '../lib/queryKeys';
import { formatBytes, formatNumber } from '../lib/formatters';
import {
  vclApi,
  addTrackingRule,
  removeTrackingRule,
  getTrackingRules,
  checkFileTracking,
} from '../api/vcl';
import { getUserRootUsage } from '../api/files';
import { vclWarningLevel } from '../components/file-manager/utils';
import type { FileItem } from '../components/file-manager/types';

export interface VclQuota {
  usagePercent: number;
  warning: 'warning' | 'critical' | null;
  current: number;
  max: number;
}

export interface UseVclFileInfoResult {
  vclQuota: VclQuota | null;
  userRootUsageBytes: number | null;
  versionCounts: Record<number, number>;
  trackingStatus: Record<number, boolean>;
  vclMode: 'automatic' | 'manual';
  toggleTracking: (file: FileItem) => Promise<void>;
  refreshVcl: () => void;
}

export function useVclFileInfo(files: FileItem[]): UseVclFileInfoResult {
  const queryClient = useQueryClient();
  const [versionCounts, setVersionCounts] = useState<Record<number, number>>({});
  const [trackingStatus, setTrackingStatus] = useState<Record<number, boolean>>({});
  const [vclMode, setVclMode] = useState<'automatic' | 'manual'>('automatic');

  const quotaQuery = useQuery({ queryKey: queryKeys.vcl.quota(), queryFn: vclApi.getUserQuota });
  const rootUsageQuery = useQuery({ queryKey: queryKeys.files.userRootUsage(), queryFn: getUserRootUsage });

  const quota = quotaQuery.data;
  const vclQuota: VclQuota | null = quota
    ? {
        usagePercent: quota.usage_percent,
        warning: vclWarningLevel(quota.usage_percent),
        current: quota.current_usage_bytes,
        max: quota.max_size_bytes,
      }
    : null;

  // Preserve the original loadVclQuota() warning/critical toast, now on quota data change.
  useEffect(() => {
    if (!quota) return;
    const level = vclWarningLevel(quota.usage_percent);
    if (level === 'critical') {
      toast.error(
        `VCL Storage Critical: ${formatNumber(quota.usage_percent, 1)}% used (${formatBytes(quota.current_usage_bytes)} / ${formatBytes(quota.max_size_bytes)})`,
        { duration: 8000 },
      );
    } else if (level === 'warning') {
      toast(
        `VCL Storage Warning: ${formatNumber(quota.usage_percent, 1)}% used (${formatBytes(quota.current_usage_bytes)} / ${formatBytes(quota.max_size_bytes)})`,
        { duration: 6000, icon: '⚠️' },
      );
    }
  }, [quota]);

  const userRootUsageBytes = rootUsageQuery.data?.user_root_used_bytes ?? null;

  // Version counts for files with a file_id (effect-based fan-out — deliberate).
  useEffect(() => {
    const loadVersionCounts = async () => {
      const fileIds = files.filter((f) => f.type === 'file' && f.file_id).map((f) => f.file_id!);
      if (fileIds.length === 0) return;
      try {
        const counts: Record<number, number> = {};
        await Promise.all(
          fileIds.map(async (fileId) => {
            try {
              const response = await vclApi.getFileVersions(fileId);
              counts[fileId] = response.total;
            } catch {
              // Ignore errors for individual files
            }
          }),
        );
        setVersionCounts(counts);
      } catch {
        // Ignore
      }
    };
    loadVersionCounts();
  }, [files]);

  // VCL mode + tracking status (effect-based fan-out — deliberate).
  useEffect(() => {
    const loadTrackingInfo = async () => {
      try {
        const rules = await getTrackingRules();
        setVclMode(rules.mode as 'automatic' | 'manual');
        const status: Record<number, boolean> = {};
        for (const rule of rules.rules) {
          if (rule.file_id) status[rule.file_id] = rule.action === 'track';
        }
        const fileIds = files.filter((f) => f.file_id).map((f) => f.file_id!);
        if (fileIds.length > 0 && fileIds.length <= 50) {
          await Promise.all(
            fileIds.map(async (fid) => {
              if (status[fid] !== undefined) return;
              try {
                const check = await checkFileTracking(fid);
                status[fid] = check.is_tracked;
              } catch {
                /* ignore */
              }
            }),
          );
        }
        setTrackingStatus(status);
      } catch {
        // Silently ignore
      }
    };
    if (files.length > 0) loadTrackingInfo();
  }, [files]);

  const toggleTracking = useCallback(
    async (file: FileItem) => {
      if (!file.file_id) return;
      const isCurrentlyTracked = trackingStatus[file.file_id] ?? (vclMode !== 'manual');
      try {
        if (isCurrentlyTracked) {
          if (vclMode === 'manual') {
            const rules = await getTrackingRules();
            const rule = rules.rules.find((r) => r.file_id === file.file_id && r.action === 'track');
            if (rule) await removeTrackingRule(rule.id);
          } else {
            await addTrackingRule({ file_id: file.file_id, action: 'exclude', is_directory: file.type === 'directory' });
          }
          setTrackingStatus((prev) => ({ ...prev, [file.file_id!]: false }));
          toast.success(`VCL disabled for ${file.name}`);
        } else {
          if (vclMode === 'automatic') {
            const rules = await getTrackingRules();
            const rule = rules.rules.find((r) => r.file_id === file.file_id && r.action === 'exclude');
            if (rule) await removeTrackingRule(rule.id);
          } else {
            await addTrackingRule({ file_id: file.file_id, action: 'track', is_directory: file.type === 'directory' });
          }
          setTrackingStatus((prev) => ({ ...prev, [file.file_id!]: true }));
          toast.success(`VCL enabled for ${file.name}`);
        }
      } catch {
        toast.error('Failed to update tracking');
      }
    },
    [trackingStatus, vclMode],
  );

  const refreshVcl = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.vcl.quota() });
    void queryClient.invalidateQueries({ queryKey: queryKeys.files.userRootUsage() });
  }, [queryClient]);

  return { vclQuota, userRootUsageBytes, versionCounts, trackingStatus, vclMode, toggleTracking, refreshVcl };
}
