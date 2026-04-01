import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { Server } from 'lucide-react';
import { SetupProgress } from '../components/setup/SetupProgress';
import { AdminSetup } from '../components/setup/AdminSetup';
import { UserSetup } from '../components/setup/UserSetup';
import { RaidSetup } from '../components/setup/RaidSetup';
import { FileAccessSetup } from '../components/setup/FileAccessSetup';
import { OptionalGate } from '../components/setup/OptionalGate';
import { SetupComplete } from '../components/setup/SetupComplete';
import { Spinner } from '../components/ui/Spinner';
import { getSetupStatus, completeSetup } from '../api/setup';
import { handleApiError } from '../lib/errorHandling';

export interface SetupWizardProps {
  onComplete: () => void;
}

// Step indices
const STEP_ADMIN = 0;
const STEP_USERS = 1;
const STEP_RAID = 2;
const STEP_FILE_ACCESS = 3;
const STEP_OPTIONAL_GATE = 4;
const STEP_COMPLETE = 5;

const REQUIRED_STEPS = 4; // Steps 0–3 are required

const STEP_LABELS = [
  'Administrator',
  'Benutzer',
  'RAID',
  'Dateizugriff',
  'Optional',
  'Fertig',
];

// Human-readable feature names for summary
const FEATURE_LABELS: Record<string, string> = {
  admin: 'Administrator-Konto',
  users: 'Benutzer-Konten',
  raid: 'RAID-Konfiguration',
  'file-access': 'Dateizugriff (Samba/WebDAV)',
};

export default function SetupWizard({ onComplete }: SetupWizardProps) {
  const [currentStep, setCurrentStep] = useState(STEP_ADMIN);
  const [setupToken, setSetupToken] = useState<string>('');
  const [configuredFeatures, setConfiguredFeatures] = useState<string[]>([]);
  const [skippedFeatures, setSkippedFeatures] = useState<string[]>([]);
  const [initializing, setInitializing] = useState(true);
  const [finishing, setFinishing] = useState(false);

  // On mount: check already completed setup steps and resume accordingly
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const status = await getSetupStatus();
        if (!status.setup_required) {
          // Setup already done — just call onComplete
          onComplete();
          return;
        }
        // Resume to the earliest incomplete required step
        const completed = status.completed_steps ?? [];
        const newConfigured: string[] = [];

        if (completed.includes('admin')) {
          newConfigured.push(FEATURE_LABELS.admin);
          if (completed.includes('users')) {
            newConfigured.push(FEATURE_LABELS.users);
            if (completed.includes('file-access')) {
              newConfigured.push(FEATURE_LABELS['file-access']);
              setCurrentStep(STEP_OPTIONAL_GATE);
            } else {
              setCurrentStep(STEP_FILE_ACCESS);
            }
          } else {
            setCurrentStep(STEP_USERS);
          }
        }

        setConfiguredFeatures(newConfigured);
      } catch {
        // Could not check setup status — start from the beginning
      } finally {
        setInitializing(false);
      }
    };

    checkStatus();
  }, [onComplete]);

  const addConfigured = (key: string) => {
    const label = FEATURE_LABELS[key];
    if (label) {
      setConfiguredFeatures((prev) =>
        prev.includes(label) ? prev : [...prev, label]
      );
    }
  };

  const addSkipped = (key: string) => {
    const label = FEATURE_LABELS[key];
    if (label) {
      setSkippedFeatures((prev) =>
        prev.includes(label) ? prev : [...prev, label]
      );
    }
  };

  // Step handlers
  const handleAdminComplete = (token: string) => {
    setSetupToken(token);
    addConfigured('admin');
    setCurrentStep(STEP_USERS);
  };

  const handleUsersComplete = () => {
    addConfigured('users');
    setCurrentStep(STEP_RAID);
  };

  const handleRaidComplete = () => {
    addConfigured('raid');
    setCurrentStep(STEP_FILE_ACCESS);
  };

  const handleRaidSkip = () => {
    addSkipped('raid');
    setCurrentStep(STEP_FILE_ACCESS);
  };

  const handleFileAccessComplete = () => {
    addConfigured('file-access');
    setCurrentStep(STEP_OPTIONAL_GATE);
  };

  const handleOptionalGateSkipAll = () => {
    setCurrentStep(STEP_COMPLETE);
  };

  const handleOptionalGateContinue = () => {
    // Future: advance into optional steps (Task 10)
    // For now, go to complete
    setCurrentStep(STEP_COMPLETE);
  };

  const handleFinish = async () => {
    if (!setupToken) {
      toast.error('Kein Setup-Token vorhanden. Bitte starten Sie das Setup neu.');
      return;
    }

    setFinishing(true);
    try {
      await completeSetup(setupToken);
      onComplete();
    } catch (err) {
      handleApiError(err, 'Fehler beim Abschließen des Setups');
    } finally {
      setFinishing(false);
    }
  };

  if (initializing) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <Spinner size="xl" label="Setup wird initialisiert..." />
      </div>
    );
  }

  // Don't show progress bar on the complete screen
  const showProgress = currentStep <= STEP_OPTIONAL_GATE;

  return (
    <div className="min-h-screen bg-gray-900 flex flex-col">
      {/* Header */}
      <div className="flex-shrink-0 pt-8 pb-4 px-4 text-center">
        <div className="flex items-center justify-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center">
            <Server className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">BaluHost</h1>
        </div>
        <p className="text-sm text-gray-400">Ersteinrichtung</p>
      </div>

      {/* Main content */}
      <div className="flex-1 flex items-start justify-center px-4 pb-12 pt-4">
        <div className="w-full max-w-2xl">
          {/* Progress bar (not shown on complete screen) */}
          {showProgress && (
            <SetupProgress
              currentStep={currentStep}
              totalSteps={STEP_LABELS.length}
              requiredSteps={REQUIRED_STEPS}
              stepLabels={STEP_LABELS}
            />
          )}

          {/* Step card */}
          <div className="bg-gray-800 rounded-2xl border border-gray-700 shadow-xl p-6 sm:p-8">
            {currentStep === STEP_ADMIN && (
              <AdminSetup onComplete={handleAdminComplete} />
            )}

            {currentStep === STEP_USERS && (
              <UserSetup
                setupToken={setupToken}
                onComplete={handleUsersComplete}
              />
            )}

            {currentStep === STEP_RAID && (
              <RaidSetup
                setupToken={setupToken}
                onComplete={handleRaidComplete}
                onSkip={handleRaidSkip}
              />
            )}

            {currentStep === STEP_FILE_ACCESS && (
              <FileAccessSetup
                setupToken={setupToken}
                onComplete={handleFileAccessComplete}
              />
            )}

            {currentStep === STEP_OPTIONAL_GATE && (
              <OptionalGate
                onSkipAll={handleOptionalGateSkipAll}
                onContinue={handleOptionalGateContinue}
              />
            )}

            {currentStep === STEP_COMPLETE && (
              <SetupComplete
                configuredFeatures={configuredFeatures}
                skippedFeatures={skippedFeatures}
                onFinish={finishing ? () => {} : handleFinish}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
