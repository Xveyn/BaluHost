import { type FormEvent, useState } from 'react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import { createArray, type AvailableDisk } from '../api/raid';
import { RAID_LEVELS, type RaidLevelInfo } from '../components/raid-setup/raidLevels';
import { isValidArrayName } from '../components/raid-setup/raidWizardHelpers';

export type WizardStep = 'select-disks' | 'raid-level' | 'confirm';

export function useRaidSetupWizard(
  availableDisks: AvailableDisk[],
  onClose: () => void,
  onSuccess: () => void,
) {
  const { t } = useTranslation('system');
  const [currentStep, setCurrentStep] = useState<WizardStep>('select-disks');
  const [selectedDisks, setSelectedDisks] = useState<string[]>([]);
  const [selectedRaidLevel, setSelectedRaidLevel] = useState<string>('raid1');
  const [arrayName, setArrayName] = useState<string>('md1');
  const [busy, setBusy] = useState<boolean>(false);

  const isArrayNameValid = isValidArrayName(arrayName);

  // Nur Disks die nicht im RAID und keine OS-Disk sind
  const freeDisks = availableDisks.filter((disk) => !disk.in_raid && !disk.is_os_disk);

  const toggleDiskSelection = (diskName: string) => {
    setSelectedDisks((prev) =>
      prev.includes(diskName) ? prev.filter((d) => d !== diskName) : [...prev, diskName]
    );
  };

  const getSelectedRaidInfo = (): RaidLevelInfo | undefined =>
    RAID_LEVELS.find((r) => r.level === selectedRaidLevel);

  const canProceedFromDiskSelection = (): boolean => selectedDisks.length >= 2;

  const canProceedFromRaidLevel = (): boolean => {
    const raidInfo = getSelectedRaidInfo();
    return raidInfo ? selectedDisks.length >= raidInfo.minDisks : false;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);

    try {
      // Use the first partition if available, otherwise pass the whole disk
      const devices = selectedDisks.map((disk) => {
        const diskObj = freeDisks.find((d) => d.name === disk);
        return diskObj?.partitions?.[0] || disk;
      });

      await createArray({
        name: arrayName,
        level: selectedRaidLevel,
        devices,
      });

      toast.success(t('raidWizard.arrayCreated', { name: arrayName }));
      onSuccess();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('raidWizard.createFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return {
    currentStep,
    setCurrentStep,
    selectedDisks,
    toggleDiskSelection,
    selectedRaidLevel,
    setSelectedRaidLevel,
    arrayName,
    setArrayName,
    busy,
    freeDisks,
    isArrayNameValid,
    getSelectedRaidInfo,
    canProceedFromDiskSelection,
    canProceedFromRaidLevel,
    handleSubmit,
  };
}
