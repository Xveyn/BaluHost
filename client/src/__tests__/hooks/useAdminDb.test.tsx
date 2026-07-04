import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useAdminTables, useAdminTableData } from '../../hooks/useAdminDb';
import * as adminDbApi from '../../api/admin-db';
import type {
  AdminTableSchemaResponse,
  AdminTableRowsResponse,
  AdminTableCategoriesResponse,
} from '../../api/admin-db';

vi.mock('../../api/admin-db');
const api = vi.mocked(adminDbApi);

const categories: AdminTableCategoriesResponse = {
  categories: { core: ['users', 'shares'] },
};

const schema: AdminTableSchemaResponse = {
  table: 'users',
  columns: [{ name: 'id', type: 'int', nullable: false }],
};

const rows: AdminTableRowsResponse = {
  table: 'users',
  page: 1,
  page_size: 25,
  rows: [{ id: 1 }],
  total: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useAdminTables', () => {
  it('loads tables and categories together', async () => {
    api.getAdminTables.mockResolvedValue(['users', 'shares']);
    api.getAdminTableCategories.mockResolvedValue(categories);

    const { result } = renderHook(() => useAdminTables(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.tables).toEqual(['users', 'shares']);
    expect(result.current.data?.categories).toEqual({ core: ['users', 'shares'] });
  });
});

describe('useAdminTableData', () => {
  const params = { page: 1, pageSize: 25 };

  it('does not fetch while no table is selected', async () => {
    const { result } = renderHook(() => useAdminTableData(null, params), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(api.getAdminTableSchema).not.toHaveBeenCalled();
    expect(api.getAdminTableRows).not.toHaveBeenCalled();
    expect(result.current.data).toBeUndefined();
  });

  it('fetches schema + rows once a table is selected', async () => {
    api.getAdminTableSchema.mockResolvedValue(schema);
    api.getAdminTableRows.mockResolvedValue(rows);

    const { result } = renderHook(() => useAdminTableData('users', params), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.schema).toEqual(schema);
    expect(result.current.data?.rows).toEqual(rows);
    expect(api.getAdminTableSchema).toHaveBeenCalledWith('users');
    expect(api.getAdminTableRows).toHaveBeenCalledWith(
      'users',
      1,
      25,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
    );
  });
});
