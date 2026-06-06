import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActivityFeed } from '../../../components/dashboard/ActivityFeed';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

const mockUseAuth = vi.fn();
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockUseActivityFeed = vi.fn();
vi.mock('../../../hooks/useActivityFeed', () => ({
  useActivityFeed: (opts: unknown) => mockUseActivityFeed(opts),
}));

afterEach(() => vi.clearAllMocks());

function setup(isAdmin: boolean) {
  mockUseAuth.mockReturnValue({ isAdmin });
  mockUseActivityFeed.mockReturnValue({ activities: [], loading: false, error: null });
  render(<ActivityFeed limit={5} />);
}

describe('ActivityFeed admin gating', () => {
  it('passes allUsers=true and shows the system-logs button for admins', () => {
    setup(true);
    expect(mockUseActivityFeed).toHaveBeenCalledWith(
      expect.objectContaining({ allUsers: true }),
    );
    expect(screen.getByText('dashboard:activity.viewSystemLogs')).toBeInTheDocument();
  });

  it('passes allUsers=false and hides the system-logs button for regular users', () => {
    setup(false);
    expect(mockUseActivityFeed).toHaveBeenCalledWith(
      expect.objectContaining({ allUsers: false }),
    );
    expect(screen.queryByText('dashboard:activity.viewSystemLogs')).not.toBeInTheDocument();
  });
});
