import type { AvailableDisk } from '../api/raid';
import { useRaidSetupWizard } from '../hooks/useRaidSetupWizard';
import { calculateArrayCapacity } from './raid-setup/raidWizardHelpers';
import {
  RaidWizardStepIndicator,
  RaidDiskSelectionStep,
  RaidLevelSelectionStep,
  RaidConfirmationStep,
} from './raid-setup';

interface RaidSetupWizardProps {
  availableDisks: AvailableDisk[];
  onClose: () => void;
  onSuccess: () => void;
}

export default function RaidSetupWizard({ availableDisks, onClose, onSuccess }: RaidSetupWizardProps) {
  const w = useRaidSetupWizard(availableDisks, onClose, onSuccess);
  const capacity = calculateArrayCapacity(w.selectedRaidLevel, w.selectedDisks.length);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl rounded-2xl border border-slate-800/60 bg-slate-900/95 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <RaidWizardStepIndicator currentStep={w.currentStep} />

        {w.currentStep === 'select-disks' && (
          <RaidDiskSelectionStep
            freeDisks={w.freeDisks}
            selectedDisks={w.selectedDisks}
            onToggleDisk={w.toggleDiskSelection}
            canProceed={w.canProceedFromDiskSelection()}
            onCancel={onClose}
            onNext={() => w.setCurrentStep('raid-level')}
          />
        )}
        {w.currentStep === 'raid-level' && (
          <RaidLevelSelectionStep
            selectedDisks={w.selectedDisks}
            selectedRaidLevel={w.selectedRaidLevel}
            onSelectLevel={w.setSelectedRaidLevel}
            canProceed={w.canProceedFromRaidLevel()}
            onBack={() => w.setCurrentStep('select-disks')}
            onCancel={onClose}
            onNext={() => w.setCurrentStep('confirm')}
          />
        )}
        {w.currentStep === 'confirm' && (
          <RaidConfirmationStep
            arrayName={w.arrayName}
            onArrayNameChange={w.setArrayName}
            isArrayNameValid={w.isArrayNameValid}
            raidInfo={w.getSelectedRaidInfo()}
            capacity={capacity}
            selectedDisks={w.selectedDisks}
            busy={w.busy}
            onBack={() => w.setCurrentStep('raid-level')}
            onCancel={onClose}
            onSubmit={w.handleSubmit}
          />
        )}
      </div>
    </div>
  );
}
