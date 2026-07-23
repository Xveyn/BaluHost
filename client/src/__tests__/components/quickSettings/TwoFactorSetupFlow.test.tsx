import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import * as twoFactorApi from '../../../api/two-factor';
import { TwoFactorSetupFlow } from '../../../components/quickSettings/TwoFactorSetupFlow';

const mockSetupData = {
  qr_code: 'data:image/png;base64,FAKE',
  provisioning_uri: 'otpauth://totp/test',
  secret: 'JBSWY3DPEHPK3PXP',
};

const mockBackupCodes = {
  backup_codes: ['CODE-0001', 'CODE-0002', 'CODE-0003'],
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('TwoFactorSetupFlow', () => {
  it('calls setup2FA on mount and renders QR + secret', async () => {
    const setup = vi.spyOn(twoFactorApi, 'setup2FA').mockResolvedValue(mockSetupData);

    render(<TwoFactorSetupFlow onComplete={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => expect(setup).toHaveBeenCalledOnce());
    // Wait for the rendered image, not just the mock call: setup2FA() runs
    // synchronously in the mount effect, while the QR only appears after the
    // promise resolves and React commits the resulting render. A synchronous
    // query hits the loading DOM once that render slips a few ms (CI, 4 workers).
    expect(await screen.findByAltText(/qr/i)).toHaveAttribute('src', mockSetupData.qr_code);
    expect(screen.getByText(mockSetupData.secret)).toBeInTheDocument();
  });

  it('cancel button calls onCancel', async () => {
    vi.spyOn(twoFactorApi, 'setup2FA').mockResolvedValue(mockSetupData);
    const onCancel = vi.fn();

    render(<TwoFactorSetupFlow onComplete={vi.fn()} onCancel={onCancel} />);

    await waitFor(() => screen.getByText(mockSetupData.secret));
    const buttons = screen.getAllByRole('button');
    // Cancel is the first plain button in the verify form
    const cancelBtn = buttons.find((b) => b.getAttribute('type') === 'button');
    fireEvent.click(cancelBtn!);
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('successful verify transitions to backup-codes step', async () => {
    vi.spyOn(twoFactorApi, 'setup2FA').mockResolvedValue(mockSetupData);
    const verify = vi.spyOn(twoFactorApi, 'verifySetup2FA').mockResolvedValue(mockBackupCodes);

    render(<TwoFactorSetupFlow onComplete={vi.fn()} onCancel={vi.fn()} />);

    await waitFor(() => screen.getByText(mockSetupData.secret));

    const codeInput = screen.getByPlaceholderText('000000') as HTMLInputElement;
    fireEvent.change(codeInput, { target: { value: '123456' } });

    const submitBtn = screen.getAllByRole('button').find((b) => b.getAttribute('type') === 'submit');
    fireEvent.click(submitBtn!);

    await waitFor(() => expect(verify).toHaveBeenCalledWith(mockSetupData.secret, '123456'));
    await waitFor(() => {
      mockBackupCodes.backup_codes.forEach((c) => expect(screen.getByText(c)).toBeInTheDocument());
    });
  });

  it('done button on backup-codes step calls onComplete', async () => {
    vi.spyOn(twoFactorApi, 'setup2FA').mockResolvedValue(mockSetupData);
    vi.spyOn(twoFactorApi, 'verifySetup2FA').mockResolvedValue(mockBackupCodes);
    const onComplete = vi.fn();

    render(<TwoFactorSetupFlow onComplete={onComplete} onCancel={vi.fn()} />);

    await waitFor(() => screen.getByText(mockSetupData.secret));
    fireEvent.change(screen.getByPlaceholderText('000000'), { target: { value: '123456' } });
    fireEvent.click(screen.getAllByRole('button').find((b) => b.getAttribute('type') === 'submit')!);

    await waitFor(() => screen.getByText(mockBackupCodes.backup_codes[0]));
    const doneBtn = screen.getAllByRole('button').find((b) => /done|fertig/i.test(b.textContent ?? ''));
    fireEvent.click(doneBtn!);

    expect(onComplete).toHaveBeenCalledOnce();
  });

  it('reports the current step via onStepChange', async () => {
    vi.spyOn(twoFactorApi, 'setup2FA').mockResolvedValue(mockSetupData);
    vi.spyOn(twoFactorApi, 'verifySetup2FA').mockResolvedValue(mockBackupCodes);
    const onStepChange = vi.fn();

    render(<TwoFactorSetupFlow onComplete={vi.fn()} onCancel={vi.fn()} onStepChange={onStepChange} />);

    await waitFor(() => screen.getByText(mockSetupData.secret));
    expect(onStepChange).toHaveBeenLastCalledWith('verify');

    fireEvent.change(screen.getByPlaceholderText('000000'), { target: { value: '123456' } });
    fireEvent.click(screen.getAllByRole('button').find((b) => b.getAttribute('type') === 'submit')!);

    await waitFor(() => expect(onStepChange).toHaveBeenLastCalledWith('backup-codes'));
  });
});
