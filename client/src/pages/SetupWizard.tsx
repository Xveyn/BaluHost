import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { BookOpen } from 'lucide-react';
import logoMark from '../assets/baluhost-logo.png';
import { SetupProgress } from '../components/setup/SetupProgress';
import { SetupWelcome } from '../components/setup/SetupWelcome';
import { AdminSetup } from '../components/setup/AdminSetup';
import { UserSetup } from '../components/setup/UserSetup';
import { RaidSetup } from '../components/setup/RaidSetup';
import { FileAccessSetup } from '../components/setup/FileAccessSetup';
import { OptionalGate } from '../components/setup/OptionalGate';
import { SharingSetup } from '../components/setup/SharingSetup';
import { VpnSetup } from '../components/setup/VpnSetup';
import { NotificationSetup } from '../components/setup/NotificationSetup';
import { CloudImportSetup } from '../components/setup/CloudImportSetup';
import { PiholeSetup } from '../components/setup/PiholeSetup';
import { DesktopSyncSetup } from '../components/setup/DesktopSyncSetup';
import { MobileAppSetup } from '../components/setup/MobileAppSetup';
import { SetupComplete } from '../components/setup/SetupComplete';
import { SetupManualDrawer } from '../components/setup/SetupManualDrawer';
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
const STEP_SHARING = 5;
const STEP_VPN = 6;
const STEP_NOTIFICATIONS = 7;
const STEP_CLOUD = 8;
const STEP_PIHOLE = 9;
const STEP_DESKTOP = 10;
const STEP_MOBILE = 11;
const STEP_COMPLETE = 12;

const REQUIRED_STEPS = 4; // Steps 0–3 are required

const STEP_LABELS = [
  'Administrator',
  'Benutzer',
  'RAID',
  'Dateizugriff',
  'Optional',
  'Freigabe',
  'VPN',
  'Benachrichtigungen',
  'Cloud',
  'Pi-hole',
  'Desktop',
  'Mobile',
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
  const [showWelcome, setShowWelcome] = useState(true);
  const [currentStep, setCurrentStep] = useState(STEP_ADMIN);
  const [setupToken, setSetupToken] = useState<string>('');
  const [configuredFeatures, setConfiguredFeatures] = useState<string[]>([]);
  const [skippedFeatures, setSkippedFeatures] = useState<string[]>([]);
  const [initializing, setInitializing] = useState(true);
  const [finishing, setFinishing] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);

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
          setShowWelcome(false);
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
    setCurrentStep(STEP_SHARING);
  };

  const handleSharingDone = () => {
    addConfigured('sharing');
    setCurrentStep(STEP_VPN);
  };

  const handleVpnDone = () => {
    addConfigured('vpn');
    setCurrentStep(STEP_NOTIFICATIONS);
  };

  const handleNotificationsDone = () => {
    addConfigured('notifications');
    setCurrentStep(STEP_CLOUD);
  };

  const handleCloudDone = () => {
    addConfigured('cloud');
    setCurrentStep(STEP_PIHOLE);
  };

  const handlePiholeDone = () => {
    addConfigured('pihole');
    setCurrentStep(STEP_DESKTOP);
  };

  const handleDesktopDone = () => {
    addConfigured('desktop');
    setCurrentStep(STEP_MOBILE);
  };

  const handleMobileDone = () => {
    addConfigured('mobile');
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
      <div className="relative flex min-h-screen items-center justify-center overflow-hidden text-slate-100">
        <Spinner size="xl" label="Setup wird initialisiert..." />
      </div>
    );
  }

  const showHeader = !showWelcome;
  const showProgress = !showWelcome && currentStep < STEP_COMPLETE;

  return (
    <div className="relative min-h-screen flex flex-col overflow-hidden text-slate-100">
      {/* Gradient blur orbs */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-24 top-[-120px] h-[420px] w-[420px] rounded-full bg-sky-500/10 blur-3xl" />
        <div className="absolute right-[-120px] top-[18%] h-[460px] w-[460px] rounded-full bg-indigo-500/10 blur-[140px]" />
        <div className="absolute left-[45%] bottom-[-180px] h-[340px] w-[340px] rounded-full bg-sky-500/5 blur-[120px]" />
      </div>

      {/* Header — hidden on welcome screen (welcome has its own logo) */}
      {showHeader && (
        <div className="relative z-10 flex-shrink-0 pt-8 pb-4 px-4 text-center">
          <div className="flex flex-col items-center gap-3 mb-2">
            <div className="glow-ring h-14 w-14">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-950 p-[2px] shadow-xl">
                <img src={logoMark} alt="BaluHost logo" className="h-full w-full rounded-full" />
              </div>
            </div>
            <h1 className="text-2xl font-semibold tracking-wide text-slate-100">BaluHost</h1>
          </div>
          <div className="flex items-center justify-center gap-3">
            <p className="text-sm text-slate-400">Ersteinrichtung</p>
            <button
              onClick={() => setManualOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700/60 bg-slate-800/50 px-2.5 py-1 text-xs text-slate-400 transition-colors hover:border-sky-500/40 hover:text-sky-400 hover:bg-slate-800/80"
              title="Benutzerhandbuch öffnen"
            >
              <BookOpen className="h-3.5 w-3.5" />
              Handbuch
            </button>
          </div>
        </div>
      )}

      {/* Main content */}
      <div className={`relative z-10 flex-1 flex justify-center px-4 pb-12 ${
        showWelcome ? 'items-center pt-4' : 'items-start pt-4'
      }`}>
        <div className="w-full max-w-2xl">
          {/* Progress bar */}
          {showProgress && (
            <SetupProgress
              currentStep={currentStep}
              totalSteps={STEP_LABELS.length}
              requiredSteps={REQUIRED_STEPS}
              stepLabels={STEP_LABELS}
            />
          )}

          {/* Card */}
          <div className="card p-6 sm:p-8">
            {showWelcome ? (
              <SetupWelcome onStart={() => setShowWelcome(false)} />
            ) : (
              <>
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

                {currentStep === STEP_SHARING && (
                  <SharingSetup
                    setupToken={setupToken}
                    onComplete={handleSharingDone}
                    onSkip={() => setCurrentStep(STEP_VPN)}
                  />
                )}

                {currentStep === STEP_VPN && (
                  <VpnSetup
                    setupToken={setupToken}
                    onComplete={handleVpnDone}
                    onSkip={() => setCurrentStep(STEP_NOTIFICATIONS)}
                  />
                )}

                {currentStep === STEP_NOTIFICATIONS && (
                  <NotificationSetup
                    setupToken={setupToken}
                    onComplete={handleNotificationsDone}
                    onSkip={() => setCurrentStep(STEP_CLOUD)}
                  />
                )}

                {currentStep === STEP_CLOUD && (
                  <CloudImportSetup
                    setupToken={setupToken}
                    onComplete={handleCloudDone}
                    onSkip={() => setCurrentStep(STEP_PIHOLE)}
                  />
                )}

                {currentStep === STEP_PIHOLE && (
                  <PiholeSetup
                    setupToken={setupToken}
                    onComplete={handlePiholeDone}
                    onSkip={() => setCurrentStep(STEP_DESKTOP)}
                  />
                )}

                {currentStep === STEP_DESKTOP && (
                  <DesktopSyncSetup
                    setupToken={setupToken}
                    onComplete={handleDesktopDone}
                    onSkip={() => setCurrentStep(STEP_MOBILE)}
                  />
                )}

                {currentStep === STEP_MOBILE && (
                  <MobileAppSetup
                    setupToken={setupToken}
                    onComplete={handleMobileDone}
                    onSkip={() => setCurrentStep(STEP_COMPLETE)}
                  />
                )}

                {currentStep === STEP_COMPLETE && (
                  <SetupComplete
                    configuredFeatures={configuredFeatures}
                    skippedFeatures={skippedFeatures}
                    onFinish={finishing ? () => {} : handleFinish}
                  />
                )}
              </>
            )}
          </div>
        </div>
      </div>

      <SetupManualDrawer open={manualOpen} onClose={() => setManualOpen(false)} />
    </div>
  );
}
