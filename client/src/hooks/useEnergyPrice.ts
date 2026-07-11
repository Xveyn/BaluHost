/**
 * useEnergyPrice -- energy price editor state (config/editing/input/saving),
 * mount fetch, and save. Extracted from PowerTab (#301).
 */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { getApiErrorMessage } from '../lib/errorHandling';
import { getEnergyPriceConfig, updateEnergyPriceConfig, type EnergyPriceConfig } from '../api/energy';

export interface UseEnergyPriceResult {
  priceConfig: EnergyPriceConfig | null;
  editingPrice: boolean;
  setEditingPrice: (v: boolean) => void;
  priceInput: string;
  setPriceInput: (v: string) => void;
  savingPrice: boolean;
  savePrice: () => Promise<void>;
}

export function useEnergyPrice(onSaved?: () => void | Promise<void>): UseEnergyPriceResult {
  const { t } = useTranslation(['system', 'common']);

  // Energy price config state (fetched once on mount; edited locally)
  const [priceConfig, setPriceConfig] = useState<EnergyPriceConfig | null>(null);
  const [editingPrice, setEditingPrice] = useState(false);
  const [priceInput, setPriceInput] = useState('');
  const [savingPrice, setSavingPrice] = useState(false);

  // Fetch price config on mount
  useEffect(() => {
    const fetchPriceConfig = async () => {
      try {
        const config = await getEnergyPriceConfig();
        setPriceConfig(config);
        setPriceInput(config.cost_per_kwh.toString());
      } catch {
        // Non-critical: price config will remain null
      }
    };
    fetchPriceConfig();
  }, []);

  const savePrice = async () => {
    const newPrice = parseFloat(priceInput);
    if (isNaN(newPrice) || newPrice < 0.01 || newPrice > 10.0) {
      toast.error(t('monitor.power.priceMustBeBetween'));
      return;
    }

    setSavingPrice(true);
    try {
      const updated = await updateEnergyPriceConfig({
        cost_per_kwh: newPrice,
        currency: priceConfig?.currency || 'EUR',
      });
      setPriceConfig(updated);
      setEditingPrice(false);
      toast.success(t('monitor.power.priceUpdated'));
      // Refresh cumulative data with the new price (active range key).
      await onSaved?.();
    } catch (err: unknown) {
      toast.error(getApiErrorMessage(err, t('monitor.power.saveError')));
    } finally {
      setSavingPrice(false);
    }
  };

  return { priceConfig, editingPrice, setEditingPrice, priceInput, setPriceInput, savingPrice, savePrice };
}
