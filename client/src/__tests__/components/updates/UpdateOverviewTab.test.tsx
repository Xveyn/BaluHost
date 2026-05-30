import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import UpdateOverviewTab from '../../../components/updates/UpdateOverviewTab';
import type { UpdateCheckResponse, VersionInfo } from '../../../api/updates';

// i18n is not initialized in component tests; the component receives `t` as a
// prop, so we pass a mock that echoes the key back.
const t = (key: string) => key;

function version(overrides: Partial<VersionInfo>): VersionInfo {
  return {
    version: '1.33.1',
    commit: 'ab14257deadbeef',
    commit_short: 'ab14257',
    tag: 'v1.33.1',
    date: null,
    is_dev_build: false,
    is_prerelease: false,
    ...overrides,
  };
}

function checkResult(current: VersionInfo): UpdateCheckResponse {
  return {
    update_available: false,
    current_version: current,
    latest_version: null,
    changelog: [],
    channel: 'stable',
    last_checked: null,
    blockers: [],
    can_update: false,
    dev_version_available: false,
    dev_version: null,
    dev_commits_ahead: null,
    dev_commits: [],
  };
}

function renderTab(current: VersionInfo) {
  return render(
    <UpdateOverviewTab
      t={t}
      checkResult={checkResult(current)}
      currentUpdate={null}
      releaseNotes={null}
      updateLoading={false}
      rollbackLoading={false}
      cancelLoading={false}
      devUpdateLoading={false}
      showUpdateConfirm={false}
      showDevUpdateConfirm={false}
      onSetShowUpdateConfirm={vi.fn()}
      onSetShowDevUpdateConfirm={vi.fn()}
      onSetShowRollbackConfirm={vi.fn()}
      onStartUpdate={vi.fn()}
      onStartDevUpdate={vi.fn()}
      onCancel={vi.fn()}
    />,
  );
}

describe('UpdateOverviewTab — stability indicator', () => {
  it('does NOT label a pre-release build as Stable', () => {
    renderTab(version({ version: '1.33.1-pre.2', tag: 'v1.33.1-pre.2', is_prerelease: true }));
    // The amber Pre-Release badge next to the version must still be present.
    expect(screen.getByText('preRelease.badge')).toBeInTheDocument();
    // The contradictory "Stable" indicator must be gone.
    expect(screen.queryByText('version.stable')).not.toBeInTheDocument();
    expect(screen.queryByText('Stable')).not.toBeInTheDocument();
  });

  it('labels a genuine stable release via the i18n key (not a hardcoded string)', () => {
    renderTab(version({ is_prerelease: false, is_dev_build: false }));
    expect(screen.getByText('version.stable')).toBeInTheDocument();
    expect(screen.queryByText('preRelease.badge')).not.toBeInTheDocument();
  });

  it('labels a dev build as Dev Build', () => {
    renderTab(version({ is_dev_build: true, tag: null }));
    expect(screen.getByText('version.devBuild')).toBeInTheDocument();
    expect(screen.queryByText('version.stable')).not.toBeInTheDocument();
  });
});
