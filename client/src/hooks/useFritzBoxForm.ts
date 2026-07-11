import { useState, useCallback } from 'react';
import toast from 'react-hot-toast';
import { testFritzBoxConnection, type FritzBoxConfig, type FritzBoxConfigUpdate } from '../api/fritzbox';

export interface FritzBoxForm {
  host: string;
  port: number;
  username: string;
  password: string;
  mac: string;
  enabled: boolean;
}

const DEFAULT_FB_FORM: FritzBoxForm = {
  host: '192.168.178.1',
  port: 49000,
  username: '',
  password: '',
  mac: '',
  enabled: false,
};

export interface UseFritzBoxFormResult {
  form: FritzBoxForm;
  update: (patch: Partial<FritzBoxForm>) => void;
  config: FritzBoxConfig | null;
  syncFromConfig: (fb: FritzBoxConfig) => void;
  toPayload: () => FritzBoxConfigUpdate;
  testing: boolean;
  test: () => Promise<void>;
}

export function useFritzBoxForm(): UseFritzBoxFormResult {
  const [form, setForm] = useState<FritzBoxForm>(DEFAULT_FB_FORM);
  const [config, setConfig] = useState<FritzBoxConfig | null>(null);
  const [testing, setTesting] = useState(false);

  const update = useCallback((patch: Partial<FritzBoxForm>) => {
    setForm((f) => ({ ...f, ...patch }));
  }, []);

  const syncFromConfig = useCallback((fb: FritzBoxConfig) => {
    setConfig(fb);
    setForm((f) => ({
      ...f,
      host: fb.host,
      port: fb.port,
      username: fb.username,
      mac: fb.nas_mac_address || '',
      enabled: fb.enabled,
      // password intentionally left as-is (API never returns it)
    }));
  }, []);

  const toPayload = useCallback((): FritzBoxConfigUpdate => ({
    host: form.host,
    port: form.port,
    username: form.username,
    ...(form.password ? { password: form.password } : {}),
    nas_mac_address: form.mac || undefined,
    enabled: form.enabled,
  }), [form]);

  const test = useCallback(async () => {
    setTesting(true);
    try {
      const result = await testFritzBoxConnection();
      if (result.success) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Connection test failed');
    } finally {
      setTesting(false);
    }
  }, []);

  return { form, update, config, syncFromConfig, toPayload, testing, test };
}
