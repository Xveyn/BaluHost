import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { queryKeys } from '../lib/queryKeys';
import { getApiErrorMessage } from '../lib/errorHandling';
import { gpuPowerApi } from '../api/gpuPower';
import type { GpuPowerCapabilities, GpuPowerConfig, GpuPowerStatus } from '../types/gpuPower';

interface GpuPowerOverview {
  status: GpuPowerStatus;
  config: GpuPowerConfig;
  caps: GpuPowerCapabilities;
}

interface UseGpuPowerReturn {
  status: GpuPowerStatus | null;
  config: GpuPowerConfig | null;
  caps: GpuPowerCapabilities | null;
  draft: GpuPowerConfig | null;
  setDraft: (config: GpuPowerConfig) => void;
  dirty: boolean;
  loadError: string | null;
  saving: boolean;
  save: () => Promise<void>;
}

/**
 * GPU-power status + config + capabilities via TanStack Query (#299), 5s poll on
 * the combined `gpuPower.overview()` key — replaces the hand-rolled setInterval.
 *
 * `draft` is the editable copy of `config`, seeded ONCE and never re-seeded by a
 * poll (draft-guard: `prev ?? config`), so a background refresh can't wipe an
 * in-progress edit. `config` still tracks the server each poll, so `dirty`
 * reflects real divergence. Saving persists the draft and re-seeds from the
 * saved config.
 */
export function useGpuPower(): UseGpuPowerReturn {
  const { t } = useTranslation(['system', 'common']);
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: queryKeys.gpuPower.overview(),
    queryFn: async (): Promise<GpuPowerOverview> => {
      const [status, config, caps] = await Promise.all([
        gpuPowerApi.getStatus(),
        gpuPowerApi.getConfig(),
        gpuPowerApi.getCapabilities(),
      ]);
      return { status, config, caps };
    },
    refetchInterval: 5000,
  });

  const status = query.data?.status ?? null;
  const config = query.data?.config ?? null;
  const caps = query.data?.caps ?? null;

  const [draft, setDraft] = useState<GpuPowerConfig | null>(null);
  useEffect(() => {
    if (config) setDraft((prev) => prev ?? config);
  }, [config]);

  const dirty = useMemo(
    () => Boolean(draft && config && JSON.stringify(draft) !== JSON.stringify(config)),
    [draft, config],
  );

  const loadError =
    query.isError && !status ? getApiErrorMessage(query.error, 'Failed to load GPU power') : null;

  const saveMutation = useMutation({
    mutationFn: (next: GpuPowerConfig) => gpuPowerApi.putConfig(next),
    onSuccess: (saved) => {
      queryClient.setQueryData<GpuPowerOverview>(queryKeys.gpuPower.overview(), (prev) =>
        prev ? { ...prev, config: saved } : prev,
      );
      setDraft(saved);
      toast.success(t('system:power.gpu.messages.saved'));
    },
    onError: (err) => {
      toast.error(`${t('system:power.gpu.messages.saveFailed')}: ${getApiErrorMessage(err, '')}`);
    },
  });

  return {
    status,
    config,
    caps,
    draft,
    setDraft,
    dirty,
    loadError,
    saving: saveMutation.isPending,
    save: async () => {
      if (draft) await saveMutation.mutateAsync(draft).catch(() => {});
    },
  };
}
