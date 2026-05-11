import { LanguageSection } from './quickSettings/LanguageSection';
import { ByteUnitSection } from './quickSettings/ByteUnitSection';
import { TwoFactorPromptSection } from './quickSettings/TwoFactorPromptSection';

interface Props {
  /** Open the 2FA setup modal. The parent is responsible for closing the
   * dropdown before showing the modal — otherwise the modal would be
   * unmounted along with this component. */
  onOpenSetup: () => void;
}

export default function UserMenuQuickSettings({ onOpenSetup }: Props) {
  return (
    <div className="flex flex-col">
      <LanguageSection />
      <div className="border-t border-slate-800/70 my-1" />
      <ByteUnitSection />
      <TwoFactorPromptSection onOpenSetup={onOpenSetup} />
    </div>
  );
}
