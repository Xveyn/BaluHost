import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DndContext } from '@dnd-kit/core';
import { SortableContext } from '@dnd-kit/sortable';
import { PillRow } from '../../../components/status-bar-config/PillRow';
import type { PillCatalogEntry } from '../../../api/statusBar';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

function wrap(entry: PillCatalogEntry, handlers = {}) {
  const props = { entry, onToggleEnabled: vi.fn(), onSetVisibility: vi.fn(), onSetDisplayMode: vi.fn(), ...handlers };
  return render(
    <DndContext>
      <SortableContext items={[entry.pill_id]}>
        <PillRow {...props} />
      </SortableContext>
    </DndContext>,
  );
}

function renderInDnd(element: React.ReactElement) {
  return render(
    <DndContext>
      <SortableContext items={['power', 'desktop', 'raid']}>
        {element}
      </SortableContext>
    </DndContext>,
  );
}

const base: PillCatalogEntry = {
  pill_id: 'power', name_key: 'statusBar.pills.power.name', enabled: false,
  visibility: 'admin', visibility_locked: false, sort_order: 0, href: '/x', icon: 'Zap',
  display_mode: 'always', display_mode_configurable: false,
};

describe('PillRow', () => {
  it('renders the pill name', () => {
    wrap(base);
    expect(screen.getByText('pills.power.name')).toBeInTheDocument();
  });

  it('calls onToggleEnabled when the enabled switch is clicked', () => {
    const onToggleEnabled = vi.fn();
    wrap(base, { onToggleEnabled });
    fireEvent.click(screen.getByRole('switch'));
    expect(onToggleEnabled).toHaveBeenCalledWith('power', true);
  });

  it('disables the visibility select for a locked pill', () => {
    wrap({ ...base, pill_id: 'raid', visibility_locked: true });
    expect(screen.getByRole('combobox')).toBeDisabled();
  });

  it('renders a display-mode select only for display_mode_configurable pills', () => {
    const baseEntry = { name_key: 'statusBar.pills.x.name', enabled: true, visibility: 'admin' as const,
                   visibility_locked: false, sort_order: 0, href: '/x', icon: 'Monitor', display_mode: 'always' as const };
    const { rerender } = renderInDnd(
      <PillRow entry={{ ...baseEntry, pill_id: 'desktop', display_mode_configurable: true }}
               onToggleEnabled={() => {}} onSetVisibility={() => {}} onSetDisplayMode={() => {}} />
    );
    expect(screen.getByLabelText('display mode')).toBeInTheDocument();
    rerender(
      <DndContext>
        <SortableContext items={['power', 'desktop', 'raid']}>
          <PillRow entry={{ ...baseEntry, pill_id: 'power', display_mode_configurable: false }}
                   onToggleEnabled={() => {}} onSetVisibility={() => {}} onSetDisplayMode={() => {}} />
        </SortableContext>
      </DndContext>
    );
    expect(screen.queryByLabelText('display mode')).not.toBeInTheDocument();
  });

  it('calls onSetDisplayMode when the select changes', () => {
    const onSetDisplayMode = vi.fn();
    renderInDnd(
      <PillRow entry={{ pill_id: 'desktop', name_key: 'statusBar.pills.desktop.name', enabled: true,
               visibility: 'admin', visibility_locked: false, sort_order: 0, href: '/x', icon: 'Monitor',
               display_mode: 'always', display_mode_configurable: true }}
               onToggleEnabled={() => {}} onSetVisibility={() => {}} onSetDisplayMode={onSetDisplayMode} />
    );
    fireEvent.change(screen.getByLabelText('display mode'), { target: { value: 'when_off' } });
    expect(onSetDisplayMode).toHaveBeenCalledWith('desktop', 'when_off');
  });
});
