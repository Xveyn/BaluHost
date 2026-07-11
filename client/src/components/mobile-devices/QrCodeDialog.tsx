import type { MobileRegistrationToken, MobileDevice } from '../../api/mobile';
import { NewTokenQrView } from './NewTokenQrView';
import { ExistingDeviceInfoView } from './ExistingDeviceInfoView';

export function QrCodeDialog({
  qrData, selectedDevice, isAdmin, showToken, onToggleToken, onClose,
}: {
  qrData: MobileRegistrationToken | null;
  selectedDevice: MobileDevice | null;
  isAdmin: boolean;
  showToken: boolean;
  onToggleToken: () => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-2 sm:p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-md h-full sm:h-auto max-h-[100vh] sm:max-h-[90vh] overflow-y-auto p-4 sm:p-6">
        <div className="flex items-center justify-between mb-4 gap-2">
          <h3 className="text-lg sm:text-xl font-semibold text-white truncate">
            {qrData ? 'QR-Code für Mobile App' : `QR-Code: ${selectedDevice?.device_name}`}
          </h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors p-2 -mr-2 touch-manipulation active:scale-95 min-w-[44px] min-h-[44px] flex items-center justify-center flex-shrink-0"
          >
            ✕
          </button>
        </div>

        {qrData ? (
          <NewTokenQrView qrData={qrData} showToken={showToken} onToggleToken={onToggleToken} />
        ) : selectedDevice ? (
          <ExistingDeviceInfoView device={selectedDevice} isAdmin={isAdmin} />
        ) : null}
      </div>
    </div>
  );
}
