/**
 * Modal for admin-triggered historical energy data import from Tapo plugs.
 * Calls POST /api/smart-devices/{id}/import-history.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';

import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import {
  importDeviceHistory,
  type ImportHistoryConflictStrategy,
  type ImportHistoryInterval,
  type ImportHistoryResponse,
} from '../../api/smart-devices';

interface TapoHistoryImportModalProps {
  deviceId: number;
  isOpen: boolean;
  onClose: () => void;
  onCompleted?: (result: ImportHistoryResponse) => void;
}

export function TapoHistoryImportModal({
  deviceId,
  isOpen,
  onClose,
  onCompleted,
}: TapoHistoryImportModalProps) {
  const { t } = useTranslation('devices');

  const [interval, setInterval] = useState<ImportHistoryInterval>('hourly');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [conflict, setConflict] = useState<ImportHistoryConflictStrategy>('live_wins');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ImportHistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setInterval('hourly');
    setStartDate('');
    setEndDate('');
    setConflict('live_wins');
    setRunning(false);
    setResult(null);
    setError(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async () => {
    setError(null);
    setResult(null);
    setRunning(true);
    try {
      const res = await importDeviceHistory(deviceId, {
        interval,
        start_date: startDate,
        end_date: endDate,
        conflict_strategy: conflict,
      });
      setResult(res);
      onCompleted?.(res);
      toast.success(
        t('historyImport.resultSummary', {
          inserted: res.samples_inserted,
          skippedIdempotent: res.samples_skipped_idempotent,
          skippedLive: res.samples_skipped_live,
          deletedLive: res.live_samples_deleted,
        }),
      );
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      toast.error(t('historyImport.errorTitle'));
    } finally {
      setRunning(false);
    }
  };

  const intervalOptions = [
    { value: 'hourly', label: t('historyImport.intervalHourly') },
    { value: 'daily', label: t('historyImport.intervalDaily') },
    { value: 'monthly', label: t('historyImport.intervalMonthly') },
  ];

  const conflictOptions = [
    { value: 'live_wins', label: t('historyImport.conflictLiveWins') },
    { value: 'import_wins', label: t('historyImport.conflictImportWins') },
  ];

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={t('historyImport.title')}>
      <div className="space-y-4">
        <p className="text-sm text-slate-300">{t('historyImport.description')}</p>

        <div className="space-y-1">
          <label className="block text-sm font-medium text-slate-200">
            {t('historyImport.intervalLabel')}
          </label>
          <Select
            value={interval}
            options={intervalOptions}
            onChange={(e) => setInterval(e.target.value as ImportHistoryInterval)}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-200">
              {t('historyImport.startLabel')}
            </label>
            <Input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-200">
              {t('historyImport.endLabel')}
            </label>
            <Input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
        </div>

        <div className="space-y-1">
          <label className="block text-sm font-medium text-slate-200">
            {t('historyImport.conflictLabel')}
          </label>
          <Select
            value={conflict}
            options={conflictOptions}
            onChange={(e) => setConflict(e.target.value as ImportHistoryConflictStrategy)}
          />
        </div>

        {error && (
          <div className="rounded-md border border-red-500/50 bg-red-500/10 p-2 text-sm text-red-400">
            {error}
          </div>
        )}

        {result && (
          <div className="rounded-md border border-emerald-500/50 bg-emerald-500/10 p-2 text-sm text-emerald-300">
            {t('historyImport.resultSummary', {
              inserted: result.samples_inserted,
              skippedIdempotent: result.samples_skipped_idempotent,
              skippedLive: result.samples_skipped_live,
              deletedLive: result.live_samples_deleted,
            })}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={handleClose} disabled={running}>
            {t('historyImport.cancel')}
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={running || !startDate || !endDate}
          >
            {running ? t('historyImport.running') : t('historyImport.submit')}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
