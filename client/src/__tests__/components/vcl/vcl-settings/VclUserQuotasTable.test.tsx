// VclUserQuotasTable.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { UserVCLStats } from '../../../../types/vcl';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { VclUserQuotasTable } from '../../../../components/vcl/vcl-settings/VclUserQuotasTable';

const user = (over: Partial<UserVCLStats> = {}): UserVCLStats => ({
  user_id: 1, username: 'alice', max_size_bytes: 1000, current_usage_bytes: 500,
  usage_percent: 50, total_versions: 4, is_enabled: true, vcl_mode: 'automatic', ...over,
});

describe('VclUserQuotasTable', () => {
  it('renders the empty-state row when there are no users', () => {
    render(<VclUserQuotasTable users={[]} onEditUser={() => {}} />);
    expect(screen.getByText('vcl.userQuotas.noUsers')).toBeInTheDocument();
  });
  it('renders a row per user and fires onEditUser with the user', () => {
    const onEditUser = vi.fn();
    render(<VclUserQuotasTable users={[user({ user_id: 9, username: 'zoe' })]} onEditUser={onEditUser} />);
    expect(screen.getByText('zoe')).toBeInTheDocument();
    fireEvent.click(screen.getByText('common.edit'));
    expect(onEditUser).toHaveBeenCalledWith(expect.objectContaining({ user_id: 9 }));
  });
  it('shows the Manual badge for manual-mode users', () => {
    render(<VclUserQuotasTable users={[user({ vcl_mode: 'manual' })]} onEditUser={() => {}} />);
    expect(screen.getByText('Manual')).toBeInTheDocument();
  });
});
