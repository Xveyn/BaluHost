import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { PermissionBadges } from '../../../components/shares/PermissionBadges';

describe('PermissionBadges', () => {
  it('renders only the granted permissions', () => {
    render(<PermissionBadges canRead canDelete />);
    expect(screen.getByText('permissions.read')).toBeInTheDocument();
    expect(screen.getByText('permissions.delete')).toBeInTheDocument();
    expect(screen.queryByText('permissions.write')).toBeNull();
  });

  it('renders nothing when no permission is granted', () => {
    const { container } = render(<PermissionBadges />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders all three when all granted', () => {
    render(<PermissionBadges canRead canWrite canDelete />);
    expect(screen.getByText('permissions.read')).toBeInTheDocument();
    expect(screen.getByText('permissions.write')).toBeInTheDocument();
    expect(screen.getByText('permissions.delete')).toBeInTheDocument();
  });
});
