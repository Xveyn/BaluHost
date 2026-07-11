/**
 * Sleep Config Panel - Configuration for sleep mode.
 *
 * Orchestrates auto-idle detection, escalation, presence, schedule, WoL,
 * Fritz!Box, and sleep-behavior settings. Form state is consolidated in
 * useSleepConfigForm / useFritzBoxForm; each section is a card in ./sleep-config.
 */

import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import {
  getSleepConfig,
  getSleepStatus,
  updateSleepConfig,
  getSleepCapabilities,
  type SleepCapabilities,
  type PresenceStatus,
} from '../../api/sleep';
import { getFritzBoxConfig, updateFritzBoxConfig } from '../../api/fritzbox';
import { useSleepConfigForm } from '../../hooks/useSleepConfigForm';
import { useFritzBoxForm } from '../../hooks/useFritzBoxForm';
import {
  CapabilitiesCard,
  IdleDetectionCard,
  EscalationCard,
  PresenceCard,
  ScheduleCard,
  WolCard,
  FritzBoxCard,
  SleepBehaviorCard,
} from './sleep-config';

export function SleepConfigPanel() {
  const [capabilities, setCapabilities] = useState<SleepCapabilities | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [coreUptimeMasterOn, setCoreUptimeMasterOn] = useState(false);
  const [alwaysAwakeOn, setAlwaysAwakeOn] = useState(false);
  const [presenceStatus, setPresenceStatus] = useState<PresenceStatus | null>(null);

  const sleepForm = useSleepConfigForm();
  const fbForm = useFritzBoxForm();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [configData, caps] = await Promise.all([
        getSleepConfig(),
        getSleepCapabilities(),
      ]);
      setCapabilities(caps);
      sleepForm.syncFromResponse(configData);

      try {
        const fb = await getFritzBoxConfig();
        fbForm.syncFromConfig(fb);
      } catch {
        // Fritz!Box config not available yet — ignore
      }
      try {
        const st = await getSleepStatus();
        setCoreUptimeMasterOn(st.core_uptime?.enabled ?? false);
        setAlwaysAwakeOn(st.always_awake?.enabled ?? false);
        setPresenceStatus(st.presence ?? null);
      } catch {
        // ignore — status is best-effort here
      }
    } catch {
      toast.error('Failed to load sleep config');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await updateSleepConfig(sleepForm.toPayload());

      try {
        await updateFritzBoxConfig(fbForm.toPayload());
      } catch {
        toast.error('Failed to save Fritz!Box config');
      }

      toast.success('Sleep configuration saved');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save config');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-700/50 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-700/50 rounded w-1/3" />
          <div className="h-40 bg-slate-700/50 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {capabilities && (
        <CapabilitiesCard capabilities={capabilities} helpOpen={helpOpen} onToggleHelp={() => setHelpOpen(!helpOpen)} />
      )}

      <IdleDetectionCard {...sleepForm.form} update={sleepForm.update} />
      <EscalationCard {...sleepForm.form} update={sleepForm.update} />
      <PresenceCard {...sleepForm.form} update={sleepForm.update} presenceStatus={presenceStatus} />
      <ScheduleCard {...sleepForm.form} update={sleepForm.update} coreUptimeMasterOn={coreUptimeMasterOn} alwaysAwakeOn={alwaysAwakeOn} />
      <WolCard {...sleepForm.form} update={sleepForm.update} capabilities={capabilities} />
      <FritzBoxCard {...fbForm.form} update={fbForm.update} config={fbForm.config} testing={fbForm.testing} onTest={fbForm.test} capabilities={capabilities} />
      <SleepBehaviorCard {...sleepForm.form} update={sleepForm.update} />

      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={busy}
          className="rounded-lg bg-teal-500/20 px-6 py-2.5 text-sm font-medium text-teal-300 hover:bg-teal-500/30 transition-colors disabled:opacity-50"
        >
          {busy ? 'Saving...' : 'Save Configuration'}
        </button>
      </div>
    </div>
  );
}
