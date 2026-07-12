import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import RaidWizardStepIndicator from '../../../components/raid-setup/RaidWizardStepIndicator';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

describe('RaidWizardStepIndicator', () => {
  it('renders the three step labels', () => {
    render(<RaidWizardStepIndicator currentStep="raid-level" />);
    expect(screen.getByText('raidWizard.steps.disks')).toBeInTheDocument();
    expect(screen.getByText('raidWizard.steps.raidLevel')).toBeInTheDocument();
    expect(screen.getByText('raidWizard.steps.confirm')).toBeInTheDocument();
  });

  it('highlights steps up to and including the current one', () => {
    // currentStep 'raid-level' => currentIndex 1: disks+raidLevel active, confirm inactive
    render(<RaidWizardStepIndicator currentStep="raid-level" />);
    expect(screen.getByText('raidWizard.steps.disks')).toHaveClass('text-slate-200');
    expect(screen.getByText('raidWizard.steps.raidLevel')).toHaveClass('text-slate-200');
    expect(screen.getByText('raidWizard.steps.confirm')).toHaveClass('text-slate-500');
  });
});
