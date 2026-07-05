import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { render, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createTestQueryClient } from '../../helpers/queryClient';

vi.mock('react-i18next', () => ({
  // Return the default string when one is given, else the key — never an options object.
  useTranslation: () => ({ t: (k: string, d?: unknown) => (typeof d === 'string' ? d : k) }),
}));
const toastSuccess = vi.fn();
vi.mock('react-hot-toast', () => ({ default: { success: (...a: unknown[]) => toastSuccess(...a), error: vi.fn() } }));
// Render the Modal body inline so we don't wrestle with portals/focus-traps.
vi.mock('../../../components/ui/Modal', () => ({
  Modal: ({ isOpen, children }: { isOpen: boolean; children: ReactNode }) =>
    isOpen ? <div>{children}</div> : null,
}));
vi.mock('../../../api/mobile', () => ({ getTokenStatus: vi.fn() }));

import { getTokenStatus } from '../../../api/mobile';
import { QrCodeDialog } from '../../../components/device-management/QrCodeDialog';

const tokenData = {
  token: 'abc123',
  qr_code: 'PHN2Zz48L3N2Zz4=',
  expires_at: new Date(0).toISOString(),
  device_token_validity_days: 30,
  vpn_config: null,
} as any;

beforeEach(() => vi.clearAllMocks());

function renderDialog(onClose = vi.fn()) {
  render(
    <QueryClientProvider client={createTestQueryClient()}>
      <QrCodeDialog data={tokenData} onClose={onClose} />
    </QueryClientProvider>,
  );
  return onClose;
}

describe('QrCodeDialog poll-until-used (query migration #299)', () => {
  it('closes the dialog and notifies once the token is used', async () => {
    (getTokenStatus as any).mockResolvedValue({ used: true });
    const onClose = renderDialog();
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(toastSuccess).toHaveBeenCalledTimes(1);
    expect(getTokenStatus).toHaveBeenCalledWith('abc123');
  });

  it('stays open while the token is unused', async () => {
    (getTokenStatus as any).mockResolvedValue({ used: false });
    const onClose = renderDialog();
    await waitFor(() => expect(getTokenStatus).toHaveBeenCalled());
    expect(onClose).not.toHaveBeenCalled();
  });
});
