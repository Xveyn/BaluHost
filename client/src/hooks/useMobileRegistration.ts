import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import type { ReactNode } from 'react';
import {
  generateMobileToken, getAvailableVpnTypes, deleteMobileDevice,
  type MobileRegistrationToken, type MobileDevice,
} from '../api/mobile';
import { queryKeys } from '../lib/queryKeys';
import { useMobileDevices } from './useMobileDevices';
import { useConfirmDialog } from './useConfirmDialog';

export interface UseMobileRegistrationResult {
  devices: MobileDevice[];
  loading: boolean;
  isFetching: boolean;
  availableVpnTypes: string[];
  deviceName: string;
  setDeviceName: (v: string) => void;
  tokenValidityDays: number;
  setTokenValidityDays: (v: number) => void;
  includeVpn: boolean;
  setIncludeVpn: (v: boolean) => void;
  vpnType: string;
  setVpnType: (v: string) => void;
  generating: boolean;
  showQrDialog: boolean;
  qrData: MobileRegistrationToken | null;
  selectedDevice: MobileDevice | null;
  showToken: boolean;
  toggleShowToken: () => void;
  handleGenerateToken: () => Promise<void>;
  handleDeleteDevice: (deviceId: string, deviceName: string) => Promise<void>;
  handleShowDeviceQr: (device: MobileDevice) => void;
  refetchDevices: () => void;
  closeQrDialog: () => void;
  dialog: ReactNode;
}

/**
 * State/handlers for MobileDevicesPage — token generation, device deletion,
 * and QR-dialog state. Extracted from MobileDevicesPage.tsx (F2/#301).
 */
export function useMobileRegistration(): UseMobileRegistrationResult {
  const { t } = useTranslation('common');
  const { confirm, dialog } = useConfirmDialog();

  const { devices, loading, isFetching, refetch: refetchDevices } = useMobileDevices();
  const { data: availableVpnTypes = [] } = useQuery({
    queryKey: queryKeys.mobile.vpnTypes(),
    queryFn: getAvailableVpnTypes,
  });

  const [qrData, setQrData] = useState<MobileRegistrationToken | null>(null);
  const [showQrDialog, setShowQrDialog] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<MobileDevice | null>(null);
  const [includeVpn, setIncludeVpn] = useState(false);
  const [vpnType, setVpnType] = useState<string>('auto');
  const [deviceName, setDeviceName] = useState('');
  const [tokenValidityDays, setTokenValidityDays] = useState(90);
  const [generating, setGenerating] = useState(false);
  const [showToken, setShowToken] = useState(false);

  const handleGenerateToken = async () => {
    if (!deviceName.trim()) {
      toast.error(t('mobile.enterDeviceName', 'Bitte Gerätenamen eingeben'));
      return;
    }
    try {
      setGenerating(true);
      const token = await generateMobileToken(includeVpn, deviceName.trim(), tokenValidityDays, vpnType);
      setQrData(token);
      try {
        const stored = { ...token, device_name: deviceName.trim(), include_vpn: includeVpn };
        localStorage.setItem('lastMobileToken', JSON.stringify(stored));
      } catch {
        // localStorage may be full or unavailable
      }
      setShowQrDialog(true);
    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : 'QR-Code konnte nicht generiert werden';
      toast.error(errorMsg);
    } finally {
      setGenerating(false);
    }
  };

  const handleDeleteDevice = async (deviceId: string, deviceName: string) => {
    const ok = await confirm(`Gerät "${deviceName}" wirklich löschen?`, { title: 'Gerät löschen', variant: 'danger', confirmLabel: 'Löschen' });
    if (!ok) return;
    try {
      await deleteMobileDevice(deviceId);
      await refetchDevices();
    } catch {
      toast.error(t('mobile.deleteFailed', 'Gerät konnte nicht gelöscht werden'));
      await refetchDevices();
    }
  };

  const handleShowDeviceQr = (device: MobileDevice) => {
    setSelectedDevice(device);
    setShowQrDialog(true);
  };

  const closeQrDialog = () => {
    setShowQrDialog(false);
    setQrData(null);
    setSelectedDevice(null);
    setDeviceName('');
    setIncludeVpn(false);
    setVpnType('auto');
    setShowToken(false);
    if (qrData) void refetchDevices();
  };

  return {
    devices, loading, isFetching, availableVpnTypes,
    deviceName, setDeviceName, tokenValidityDays, setTokenValidityDays,
    includeVpn, setIncludeVpn, vpnType, setVpnType, generating,
    showQrDialog, qrData, selectedDevice, showToken,
    toggleShowToken: () => setShowToken((s) => !s),
    handleGenerateToken, handleDeleteDevice, handleShowDeviceQr,
    refetchDevices, closeQrDialog, dialog,
  };
}
