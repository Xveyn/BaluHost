import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { UserVCLStats, VCLSettingsUpdate } from '../../../../types/vcl';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { VclEditUserModal } from '../../../../components/vcl/vcl-settings/VclEditUserModal';

const editingUser: UserVCLStats = {
  user_id: 1, username: 'alice', max_size_bytes: 1000, current_usage_bytes: 500,
  usage_percent: 50, total_versions: 4, is_enabled: true, vcl_mode: 'automatic',
};
const editForm: VCLSettingsUpdate = { max_size_bytes: 1000, is_enabled: true };
const base = { editingUser, editForm, actionLoading: false,
  onMaxSizeChange: () => {}, onEnabledChange: () => {}, onCancel: () => {}, onSave: () => {} };

describe('VclEditUserModal', () => {
  it('fires onSave and onCancel from the footer buttons', () => {
    const onSave = vi.fn(), onCancel = vi.fn();
    render(<VclEditUserModal {...base} onSave={onSave} onCancel={onCancel} />);
    fireEvent.click(screen.getByText('common.save'));
    fireEvent.click(screen.getByText('common.cancel'));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
  it('fires onEnabledChange when the enable checkbox toggles', () => {
    const onEnabledChange = vi.fn();
    render(<VclEditUserModal {...base} onEnabledChange={onEnabledChange} />);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(onEnabledChange).toHaveBeenCalledWith(false);
  });
});
