import { type FormEvent, useState } from 'react';
import toast from 'react-hot-toast';
import { createArray, type AvailableDisk } from '../api/raid';

interface RaidSetupWizardProps {
  availableDisks: AvailableDisk[];
  onClose: () => void;
  onSuccess: () => void;
}

type WizardStep = 'select-disks' | 'raid-level' | 'confirm';

interface RaidLevelInfo {
  level: string;
  name: string;
  description: string;
  minDisks: number;
  redundancy: string;
  capacity: string;
  performance: string;
  recommended?: boolean;
}

const RAID_LEVELS: RaidLevelInfo[] = [
  {
    level: 'raid1',
    name: 'RAID 1 (Mirroring)',
    description: 'All data is mirrored across multiple disks. Maximum security through redundancy.',
    minDisks: 2,
    redundancy: 'High (n-1 disks can fail)',
    capacity: '50% (with 2 disks)',
    performance: 'Read: Good / Write: Medium',
    recommended: true,
  },
  {
    level: 'raid0',
    name: 'RAID 0 (Striping)',
    description: 'Data is distributed across multiple disks. Maximum speed but no redundancy.',
    minDisks: 2,
    redundancy: 'None (failure = data loss)',
    capacity: '100%',
    performance: 'Read: Excellent / Write: Excellent',
  },
  {
    level: 'raid5',
    name: 'RAID 5 (Parity)',
    description: 'Data distributed with parity information. Good balance between speed and security.',
    minDisks: 3,
    redundancy: 'Medium (1 disk can fail)',
    capacity: '(n-1)/n × 100%',
    performance: 'Read: Good / Write: Medium',
  },
  {
    level: 'raid6',
    name: 'RAID 6 (Double Parity)',
    description: 'Like RAID 5, but with double parity information. Higher security than RAID 5.',
    minDisks: 4,
    redundancy: 'High (2 disks can fail)',
    capacity: '(n-2)/n × 100%',
    performance: 'Read: Good / Write: Low',
  },
  {
    level: 'raid10',
    name: 'RAID 10 (Mirrored Stripe)',
    description: 'Combination of RAID 0 and RAID 1. High speed with redundancy.',
    minDisks: 4,
    redundancy: 'High (n/2 disks can fail)',
    capacity: '50%',
    performance: 'Read: Excellent / Write: Good',
  },
];

const formatBytes = (bytes: number): string => {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return '0 B';
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const size = bytes / 1024 ** exponent;
  return `${size >= 100 ? Math.round(size) : size.toFixed(1)} ${units[exponent]}`;
};

export default function RaidSetupWizard({ availableDisks, onClose, onSuccess }: RaidSetupWizardProps) {
  const [currentStep, setCurrentStep] = useState<WizardStep>('select-disks');
  const [selectedDisks, setSelectedDisks] = useState<string[]>([]);
  const [selectedRaidLevel, setSelectedRaidLevel] = useState<string>('raid1');
  const [arrayName, setArrayName] = useState<string>('md1');
  const [busy, setBusy] = useState<boolean>(false);

  // Nur Disks die nicht im RAID sind
  const freeDisks = availableDisks.filter((disk) => !disk.in_raid);

  const toggleDiskSelection = (diskName: string) => {
    setSelectedDisks((prev) =>
      prev.includes(diskName) ? prev.filter((d) => d !== diskName) : [...prev, diskName]
    );
  };

  const getSelectedRaidInfo = (): RaidLevelInfo | undefined => {
    return RAID_LEVELS.find((r) => r.level === selectedRaidLevel);
  };

  const canProceedFromDiskSelection = (): boolean => {
    return selectedDisks.length >= 2;
  };

  const canProceedFromRaidLevel = (): boolean => {
    const raidInfo = getSelectedRaidInfo();
    return raidInfo ? selectedDisks.length >= raidInfo.minDisks : false;
  };

  const calculateArrayCapacity = (): string => {
    const raidInfo = getSelectedRaidInfo();
    if (!raidInfo || selectedDisks.length === 0) return '0 GB';

    const diskSize = 5 * 1024 ** 3; // 5 GB per disk in dev mode
    const count = selectedDisks.length;

    let capacity = 0;
    switch (raidInfo.level) {
      case 'raid0':
        capacity = diskSize * count;
        break;
      case 'raid1':
        capacity = diskSize;
        break;
      case 'raid5':
        capacity = diskSize * (count - 1);
        break;
      case 'raid6':
        capacity = diskSize * (count - 2);
        break;
      case 'raid10':
        capacity = diskSize * (count / 2);
        break;
      default:
        capacity = diskSize;
    }

    return formatBytes(capacity);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);

    try {
      // Konvertiere Disk-Namen zu Partition-Namen (z.B. sdc -> sdc1)
      const devices = selectedDisks.map((disk) => {
        const diskObj = freeDisks.find((d) => d.name === disk);
        return diskObj?.partitions?.[0] || `${disk}1`;
      });

      await createArray({
        name: arrayName,
        level: selectedRaidLevel,
        devices,
      });

      toast.success(`RAID Array ${arrayName} successfully created`);
      onSuccess();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create array';
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const renderStepIndicator = () => {
    const steps = [
      { id: 'select-disks', label: 'Disks' },
      { id: 'raid-level', label: 'RAID-Level' },
      { id: 'confirm', label: 'Bestätigung' },
    ];

    const currentIndex = steps.findIndex((s) => s.id === currentStep);

    return (
      <div className="flex items-center justify-center space-x-2 mb-8">
        {steps.map((step, index) => (
          <div key={step.id} className="flex items-center">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold transition ${
                index <= currentIndex
                  ? 'bg-sky-500/20 text-sky-200 border-2 border-sky-500'
                  : 'bg-slate-800/60 text-slate-500 border-2 border-slate-700'
              }`}
            >
              {index + 1}
            </div>
            <span
              className={`ml-2 text-sm font-medium ${
                index <= currentIndex ? 'text-slate-200' : 'text-slate-500'
              }`}
            >
              {step.label}
            </span>
            {index < steps.length - 1 && (
              <div
                className={`mx-4 h-0.5 w-12 ${
                  index < currentIndex ? 'bg-sky-500' : 'bg-slate-700'
                }`}
              />
            )}
          </div>
        ))}
      </div>
    );
  };

  const renderDiskSelection = () => (
    <div>
      <h3 className="text-xl font-semibold text-white">Select Disks</h3>
      <p className="mt-1 text-sm text-slate-400">
        Choose the disks you want to use for the RAID array.
      </p>

      <div className="mt-6 space-y-3">
        {freeDisks.length === 0 ? (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-center">
            <p className="text-sm text-amber-200">
              No available disks found. All disks are already in a RAID array.
            </p>
          </div>
        ) : (
          freeDisks.map((disk) => (
            <button
              key={disk.name}
              type="button"
              onClick={() => toggleDiskSelection(disk.name)}
              className={`w-full rounded-lg border p-4 text-left transition ${
                selectedDisks.includes(disk.name)
                  ? 'border-sky-500 bg-sky-500/15'
                  : 'border-slate-700/70 bg-slate-900/60 hover:border-slate-600'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div
                    className={`flex h-5 w-5 items-center justify-center rounded border-2 transition ${
                      selectedDisks.includes(disk.name)
                        ? 'border-sky-500 bg-sky-500'
                        : 'border-slate-600 bg-slate-900'
                    }`}
                  >
                    {selectedDisks.includes(disk.name) && (
                      <svg className="h-3 w-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    )}
                  </div>
                  <div>
                    <p className="font-medium text-slate-200">/dev/{disk.name}</p>
                    <p className="text-xs text-slate-400">{disk.model || 'Unbekanntes Modell'}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-slate-300">{formatBytes(disk.size_bytes)}</p>
                  {disk.partitions.length > 0 && (
                    <p className="text-xs text-slate-500">
                      {disk.partitions.length} Partition{disk.partitions.length > 1 ? 'en' : ''}
                    </p>
                  )}
                </div>
              </div>
            </button>
          ))
        )}
      </div>

      {selectedDisks.length > 0 && (
        <div className="mt-4 rounded-lg border border-slate-700/70 bg-slate-900/60 p-3">
          <p className="text-sm text-slate-300">
            <span className="font-medium text-white">{selectedDisks.length}</span> Disk
            {selectedDisks.length > 1 ? 'n' : ''} ausgewählt
          </p>
        </div>
      )}

      <div className="mt-6 flex justify-end gap-3">
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
        >
          Abbrechen
        </button>
        <button
          type="button"
          onClick={() => setCurrentStep('raid-level')}
          disabled={!canProceedFromDiskSelection()}
          className={`rounded-lg border px-4 py-2 text-sm transition ${
            canProceedFromDiskSelection()
              ? 'border-sky-500/40 bg-sky-500/15 text-sky-100 hover:border-sky-500/60'
              : 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
          }`}
        >
          Weiter
        </button>
      </div>
    </div>
  );

  const renderRaidLevelSelection = () => {
    const availableRaidLevels = RAID_LEVELS.filter((r) => selectedDisks.length >= r.minDisks);

    return (
      <div>
        <h3 className="text-xl font-semibold text-white">Select RAID Level</h3>
        <p className="mt-1 text-sm text-slate-400">
          Choose the appropriate RAID level for your setup with {selectedDisks.length} disks.
        </p>

        <div className="mt-6 space-y-3">
          {availableRaidLevels.map((raid) => (
            <button
              key={raid.level}
              type="button"
              onClick={() => setSelectedRaidLevel(raid.level)}
              className={`w-full rounded-lg border p-4 text-left transition ${
                selectedRaidLevel === raid.level
                  ? 'border-sky-500 bg-sky-500/15'
                  : 'border-slate-700/70 bg-slate-900/60 hover:border-slate-600'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <p className="font-semibold text-white">{raid.name}</p>
                    {raid.recommended && (
                      <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-medium text-emerald-200">
                        Empfohlen
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-sm text-slate-400">{raid.description}</p>

                  <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <p className="text-slate-500">Redundanz</p>
                      <p className="text-slate-300">{raid.redundancy}</p>
                    </div>
                    <div>
                      <p className="text-slate-500">Kapazität</p>
                      <p className="text-slate-300">{raid.capacity}</p>
                    </div>
                    <div className="col-span-2">
                      <p className="text-slate-500">Performance</p>
                      <p className="text-slate-300">{raid.performance}</p>
                    </div>
                  </div>
                </div>
                <div
                  className={`ml-4 flex h-5 w-5 items-center justify-center rounded-full border-2 transition ${
                    selectedRaidLevel === raid.level
                      ? 'border-sky-500 bg-sky-500'
                      : 'border-slate-600 bg-slate-900'
                  }`}
                >
                  {selectedRaidLevel === raid.level && (
                    <div className="h-2 w-2 rounded-full bg-white" />
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>

        <div className="mt-6 flex justify-between gap-3">
          <button
            type="button"
            onClick={() => setCurrentStep('select-disks')}
            className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
          >
            Back
          </button>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
            >
              Abbrechen
            </button>
            <button
              type="button"
              onClick={() => setCurrentStep('confirm')}
              disabled={!canProceedFromRaidLevel()}
              className={`rounded-lg border px-4 py-2 text-sm transition ${
                canProceedFromRaidLevel()
                  ? 'border-sky-500/40 bg-sky-500/15 text-sky-100 hover:border-sky-500/60'
                  : 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
              }`}
            >
              Next
            </button>
          </div>
        </div>
      </div>
    );
  };

  const renderConfirmation = () => {
    const raidInfo = getSelectedRaidInfo();
    const capacity = calculateArrayCapacity();

    return (
      <form onSubmit={handleSubmit}>
        <h3 className="text-xl font-semibold text-white">Confirm Configuration</h3>
        <p className="mt-2 text-sm text-slate-400">Review your RAID configuration before creating.</p>

        <div className="mt-6 space-y-4">
          {/* Array Name */}
          <div>
            <label className="block text-sm font-medium text-slate-300">Array-Name</label>
            <input
              type="text"
              value={arrayName}
              onChange={(e) => setArrayName(e.target.value)}
              required
              placeholder="z.B. md1"
              className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
            />
          </div>

          {/* Configuration Summary */}
          <div className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-4">
            <h4 className="font-medium text-white">Zusammenfassung</h4>

            <div className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-400">RAID-Level:</span>
                <span className="font-medium text-slate-200">{raidInfo?.name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Anzahl Festplatten:</span>
                <span className="font-medium text-slate-200">{selectedDisks.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Verfügbare Kapazität:</span>
                <span className="font-medium text-emerald-200">{capacity}</span>
              </div>
            </div>

            <div className="mt-4 border-t border-slate-800 pt-3">
              <p className="text-xs font-medium text-slate-400">Selected Disks:</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {selectedDisks.map((disk) => (
                  <span
                    key={disk}
                    className="rounded-md bg-slate-800/60 px-2 py-1 text-xs font-medium text-slate-300"
                  >
                    /dev/{disk}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Warning */}
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
            <div className="flex items-start gap-3">
              <svg
                className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-400"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                  clipRule="evenodd"
                />
              </svg>
              <div>
                <p className="text-sm font-medium text-amber-200">Wichtiger Hinweis</p>
                <p className="mt-1 text-xs text-amber-200/80">
                  All data on the selected disks will be deleted. Make sure you have
                  created backups before proceeding.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-6 flex justify-between gap-3">
          <button
            type="button"
            onClick={() => setCurrentStep('raid-level')}
            className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
          >
            Zurück
          </button>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
            >
              Abbrechen
            </button>
            <button
              type="submit"
              disabled={busy}
              className={`rounded-lg border px-4 py-2 text-sm transition ${
                busy
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                  : 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/60'
              }`}
            >
              {busy ? 'Wird erstellt...' : 'Array erstellen'}
            </button>
          </div>
        </div>
      </form>
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl rounded-2xl border border-slate-800/60 bg-slate-900/95 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {renderStepIndicator()}

        {currentStep === 'select-disks' && renderDiskSelection()}
        {currentStep === 'raid-level' && renderRaidLevelSelection()}
        {currentStep === 'confirm' && renderConfirmation()}
      </div>
    </div>
  );
}
