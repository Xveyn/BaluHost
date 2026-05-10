import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from './ui/Modal';
import { LanguageSection } from './quickSettings/LanguageSection';
import { ByteUnitSection } from './quickSettings/ByteUnitSection';
import { TwoFactorPromptSection } from './quickSettings/TwoFactorPromptSection';
import { TwoFactorSetupFlow, type TwoFactorSetupStep } from './quickSettings/TwoFactorSetupFlow';
import { refreshStatus } from './quickSettings/twoFactorStatusStore';

export default function UserMenuQuickSettings() {
  const { t } = useTranslation('common');
  const [setupOpen, setSetupOpen] = useState(false);
  const [setupStep, setSetupStep] = useState<TwoFactorSetupStep>('loading');

  const handleSetupComplete = () => {
    refreshStatus();
    setSetupOpen(false);
  };

  // Backup-codes step must not be dismissable by accident
  const lockClose = setupStep === 'backup-codes';

  return (
    <div className="flex flex-col">
      <LanguageSection />
      <div className="border-t border-slate-800/70 my-1" />
      <ByteUnitSection />
      <TwoFactorPromptSection onOpenSetup={() => setSetupOpen(true)} />

      <Modal
        isOpen={setupOpen}
        onClose={() => setSetupOpen(false)}
        title={t('userMenu.quickSettings.twoFactor.modalTitle')}
        size="lg"
        closeOnOverlayClick={!lockClose}
        closeOnEscape={!lockClose}
      >
        <TwoFactorSetupFlow
          onComplete={handleSetupComplete}
          onCancel={() => setSetupOpen(false)}
          onStepChange={setSetupStep}
        />
      </Modal>
    </div>
  );
}
