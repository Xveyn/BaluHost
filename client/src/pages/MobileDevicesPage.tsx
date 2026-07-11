import { useMobileRegistration } from '../hooks/useMobileRegistration';
import { useAuth } from '../contexts/AuthContext';
import { RegisterDeviceCard, MobileDevicesList, QrCodeDialog } from '../components/mobile-devices';

export default function MobileDevicesPage() {
  const { isAdmin } = useAuth();
  const {
    devices, loading, isFetching, availableVpnTypes,
    deviceName, setDeviceName, tokenValidityDays, setTokenValidityDays,
    includeVpn, setIncludeVpn, vpnType, setVpnType, generating,
    showQrDialog, qrData, selectedDevice, showToken, toggleShowToken,
    handleGenerateToken, handleDeleteDevice, handleShowDeviceQr,
    refetchDevices, closeQrDialog, dialog,
  } = useMobileRegistration();

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <h1 className="text-2xl sm:text-3xl font-semibold text-white mb-2">Mobile Geräte</h1>
        <p className="text-sm text-slate-400">Verwalte deine mobilen BaluHost-Apps</p>
      </div>

      <RegisterDeviceCard
        deviceName={deviceName}
        onDeviceNameChange={setDeviceName}
        tokenValidityDays={tokenValidityDays}
        onValidityChange={setTokenValidityDays}
        includeVpn={includeVpn}
        onIncludeVpnChange={setIncludeVpn}
        vpnType={vpnType}
        onVpnTypeChange={setVpnType}
        availableVpnTypes={availableVpnTypes}
        generating={generating}
        onGenerate={handleGenerateToken}
      />

      <MobileDevicesList
        devices={devices}
        loading={loading}
        isFetching={isFetching}
        isAdmin={isAdmin}
        onRefresh={refetchDevices}
        onShowQr={handleShowDeviceQr}
        onDelete={handleDeleteDevice}
      />

      {showQrDialog && (qrData || selectedDevice) && (
        <QrCodeDialog
          qrData={qrData}
          selectedDevice={selectedDevice}
          isAdmin={isAdmin}
          showToken={showToken}
          onToggleToken={toggleShowToken}
          onClose={closeQrDialog}
        />
      )}
      {dialog}
    </div>
  );
}
