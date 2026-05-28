import { useCallback, useEffect, useState } from 'react';
import { getStatusBarConfig, updateStatusBarConfig } from '../../api/statusBar';
import type { PillCatalogEntry, PillVisibility } from '../../api/statusBar';

export interface UsePillConfig {
  pills: PillCatalogEntry[];
  showBottomUpload: boolean;
  loading: boolean;
  saving: boolean;
  error: boolean;
  setEnabled: (id: string, enabled: boolean) => void;
  setVisibility: (id: string, visibility: PillVisibility) => void;
  setShowBottomUpload: (v: boolean) => void;
  reorder: (from: number, to: number) => void;
  save: () => Promise<void>;
  reload: () => Promise<void>;
}

function reindex(pills: PillCatalogEntry[]): PillCatalogEntry[] {
  return pills.map((p, i) => ({ ...p, sort_order: i }));
}

export function usePillConfig(): UsePillConfig {
  const [pills, setPills] = useState<PillCatalogEntry[]>([]);
  const [showBottomUpload, setShow] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const cfg = await getStatusBarConfig();
      setPills([...cfg.pills].sort((a, b) => a.sort_order - b.sort_order));
      setShow(cfg.show_bottom_upload);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const setEnabled = useCallback((id: string, enabled: boolean) => {
    setPills(prev => prev.map(p => (p.pill_id === id ? { ...p, enabled } : p)));
  }, []);

  const setVisibility = useCallback((id: string, visibility: PillVisibility) => {
    setPills(prev => prev.map(p => (p.pill_id === id ? { ...p, visibility } : p)));
  }, []);

  const reorder = useCallback((from: number, to: number) => {
    setPills(prev => {
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return reindex(next);
    });
  }, []);

  const save = useCallback(async () => {
    setSaving(true);
    try {
      await updateStatusBarConfig({
        pills: pills.map(p => ({
          pill_id: p.pill_id, enabled: p.enabled,
          visibility: p.visibility, sort_order: p.sort_order,
        })),
        show_bottom_upload: showBottomUpload,
      });
    } finally {
      setSaving(false);
    }
  }, [pills, showBottomUpload]);

  return {
    pills, showBottomUpload, loading, saving, error,
    setEnabled, setVisibility, setShowBottomUpload: setShow, reorder, save, reload,
  };
}
