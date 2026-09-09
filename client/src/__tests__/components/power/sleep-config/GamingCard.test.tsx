import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { GamingCard } from '../../../../components/power/sleep-config/GamingCard';
import type { GamingStatus } from '../../../../api/sleep';

const status = (over: Partial<GamingStatus> = {}): GamingStatus => ({
  game_running: false,
  gaming_mode: false,
  block_in_gaming_mode: true,
  suppressing_suspend: false,
  ...over,
});

const base = { blockSuspendInGamingMode: true, update: vi.fn(), gamingStatus: null };

describe('GamingCard', () => {
  it('renders the Big Picture toggle', () => {
    render(<GamingCard {...base} />);
    expect(screen.getByText('sleep.gaming.title')).toBeInTheDocument();
    expect(screen.getByText('sleep.gaming.bigPictureLabel')).toBeInTheDocument();
  });

  it('toggling the setting calls update', () => {
    const update = vi.fn();
    render(<GamingCard {...base} update={update} />);
    fireEvent.click(screen.getAllByRole('button')[0]);
    expect(update).toHaveBeenCalledWith({ blockSuspendInGamingMode: false });
  });

  it('says a running game is holding the box awake', () => {
    render(
      <GamingCard
        {...base}
        gamingStatus={status({ game_running: true, suppressing_suspend: true })}
      />,
    );
    expect(screen.getByText('sleep.gaming.gameRunning')).toBeInTheDocument();
  });

  it('distinguishes Big Picture from a running game', () => {
    render(
      <GamingCard
        {...base}
        gamingStatus={status({ gaming_mode: true, suppressing_suspend: true })}
      />,
    );
    expect(screen.getByText('sleep.gaming.bigPictureActive')).toBeInTheDocument();
    expect(screen.queryByText('sleep.gaming.gameRunning')).not.toBeInTheDocument();
  });

  it('says Big Picture is being ignored when the toggle is off', () => {
    render(
      <GamingCard
        {...base}
        blockSuspendInGamingMode={false}
        gamingStatus={status({ gaming_mode: true, suppressing_suspend: false })}
      />,
    );
    expect(screen.getByText('sleep.gaming.bigPictureIgnored')).toBeInTheDocument();
  });

  it('stays quiet when nothing is holding the box awake', () => {
    render(<GamingCard {...base} gamingStatus={status()} />);
    expect(screen.queryByText('sleep.gaming.gameRunning')).not.toBeInTheDocument();
    expect(screen.queryByText('sleep.gaming.bigPictureActive')).not.toBeInTheDocument();
  });

  it('always announces a running game, even with the toggle off', () => {
    render(
      <GamingCard
        {...base}
        blockSuspendInGamingMode={false}
        gamingStatus={status({ game_running: true, suppressing_suspend: true })}
      />,
    );
    expect(screen.getByText('sleep.gaming.gameRunning')).toBeInTheDocument();
  });
});
