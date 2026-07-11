import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../api/fritzbox', () => ({ testFritzBoxConnection: vi.fn() }));

import toast from 'react-hot-toast';
import { testFritzBoxConnection, type FritzBoxConfig } from '../../api/fritzbox';
import { useFritzBoxForm } from '../../hooks/useFritzBoxForm';

const fb: FritzBoxConfig = {
  host: '192.168.1.1', port: 12345, username: 'admin',
  nas_mac_address: '11:22:33:44:55:66', enabled: true, has_password: true,
};

beforeEach(() => vi.clearAllMocks());

describe('useFritzBoxForm', () => {
  it('syncFromConfig fills the form but leaves password empty', () => {
    const { result } = renderHook(() => useFritzBoxForm());
    act(() => result.current.syncFromConfig(fb));
    expect(result.current.form.host).toBe('192.168.1.1');
    expect(result.current.form.mac).toBe('11:22:33:44:55:66');
    expect(result.current.form.enabled).toBe(true);
    expect(result.current.form.password).toBe('');
    expect(result.current.config?.has_password).toBe(true);
  });

  it('toPayload omits password when empty and maps empty mac to undefined', () => {
    const { result } = renderHook(() => useFritzBoxForm());
    act(() => result.current.update({ host: 'h', port: 1, username: 'u', mac: '', enabled: false }));
    const payload = result.current.toPayload();
    expect('password' in payload).toBe(false);
    expect(payload.nas_mac_address).toBeUndefined();
    expect(payload).toMatchObject({ host: 'h', port: 1, username: 'u', enabled: false });
  });

  it('toPayload includes password when set', () => {
    const { result } = renderHook(() => useFritzBoxForm());
    act(() => result.current.update({ password: 'secret' }));
    expect(result.current.toPayload().password).toBe('secret');
  });

  it('test() toasts success/error and clears testing', async () => {
    (testFritzBoxConnection as any).mockResolvedValue({ success: true, message: 'OK' });
    const { result } = renderHook(() => useFritzBoxForm());
    await act(async () => { await result.current.test(); });
    expect(toast.success).toHaveBeenCalledWith('OK');
    expect(result.current.testing).toBe(false);

    (testFritzBoxConnection as any).mockResolvedValue({ success: false, message: 'bad' });
    await act(async () => { await result.current.test(); });
    expect(toast.error).toHaveBeenCalledWith('bad');
  });
});
