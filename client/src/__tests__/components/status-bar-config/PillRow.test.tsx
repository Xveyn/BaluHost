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
  const props = { entry, onToggleEnabled: vi.fn(), onSetVisibility: vi.fn(), ...handlers };
  return render(
    <DndContext>
      <SortableContext items={[entry.pill_id]}>
        <PillRow {...props} />
      </SortableContext>
    </DndContext>,
  );
}

const base: PillCatalogEntry = {
  pill_id: 'power', name_key: 'statusBar.pills.power.name', enabled: false,
  visibility: 'admin', visibility_locked: false, sort_order: 0, href: '/x',
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
});
