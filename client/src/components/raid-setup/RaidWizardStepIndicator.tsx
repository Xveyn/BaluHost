import { useTranslation } from 'react-i18next';
import type { WizardStep } from '../../hooks/useRaidSetupWizard';

interface RaidWizardStepIndicatorProps {
  currentStep: WizardStep;
}

export default function RaidWizardStepIndicator({ currentStep }: RaidWizardStepIndicatorProps) {
  const { t } = useTranslation('system');
  const steps = [
    { id: 'select-disks', label: t('raidWizard.steps.disks') },
    { id: 'raid-level', label: t('raidWizard.steps.raidLevel') },
    { id: 'confirm', label: t('raidWizard.steps.confirm') },
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
}
