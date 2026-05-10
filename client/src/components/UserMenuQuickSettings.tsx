import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Modal } from './ui/Modal';
import { LanguageSection } from './quickSettings/LanguageSection';
import { ByteUnitSection } from './quickSettings/ByteUnitSection';
import { TwoFactorPromptSection } from './quickSettings/TwoFactorPromptSection';
import { TwoFactorSetupFlow, type TwoFactorSetupStep } from './quickSettings/TwoFactorSetupFlow';
import { refreshStatus } from './quickSettings/twoFactorStatusStore';

interface Props {
  /** Called when an action inside Quick-Settings should also close the parent dropdown
   * (e.g., before opening the 2FA setup Modal so the dropdown does not remain
   * mounted behind it). */
  onCloseDropdown: () => void;
}

export default function UserMenuQuickSettings({ onCloseDropdown }: Props) {
  const { t } = useTranslation('common');
  const [setupOpen, setSetupOpen] = useState(false);
  const [setupStep, setSetupStep] = useState<TwoFactorSetupStep>('loading');

  const handleOpenSetup = () => {
    onCloseDropdown();
    setSetupOpen(true);
  };

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
      <TwoFactorPromptSection onOpenSetup={handleOpenSetup} />

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
