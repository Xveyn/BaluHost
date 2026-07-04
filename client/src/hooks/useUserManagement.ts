import { useState, useEffect, useRef, useCallback, useMemo, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { handleApiError, getApiErrorMessage } from '../lib/errorHandling';
import { queryKeys } from '../lib/queryKeys';
import { useConfirmDialog } from './useConfirmDialog';
import {
  listUsers,
  createUser,
  updateUser,
  deleteUser,
  bulkDeleteUsers,
  toggleUserActive,
  type UserPublic,
  type CreateUserPayload,
  type UpdateUserPayload,
} from '../api/users';

export interface UserFormData {
  username: string;
  email: string;
  password: string;
  role: string;
  is_active: boolean;
}

interface UserStats {
  total: number;
  active: number;
  inactive: number;
  admins: number;
}

export function useUserManagement() {
  const { t } = useTranslation(['admin', 'common']);

  const queryClient = useQueryClient();

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc' | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  // Selection
  const [selectedUsers, setSelectedUsers] = useState<Set<number>>(new Set());

  // Confirm dialog
  const { confirm, dialog: confirmDialog } = useConfirmDialog();

  // Debounce search input (300ms)
  useEffect(() => {
    debounceRef.current = setTimeout(() => setDebouncedSearch(searchTerm), 300);
    return () => clearTimeout(debounceRef.current);
  }, [searchTerm]);

  // Load users — TanStack Query keyed on the active filters/sort, so changing any
  // of them refetches. Search is debounced above. No polling.
  const listParams = useMemo(
    () => ({
      search: debouncedSearch || undefined,
      role: roleFilter || undefined,
      is_active: statusFilter || undefined,
      sort_by: sortBy || undefined,
      sort_order: sortBy && sortOrder ? sortOrder : undefined,
    }),
    [debouncedSearch, roleFilter, statusFilter, sortBy, sortOrder],
  );

  const query = useQuery({
    queryKey: queryKeys.users.list(listParams),
    queryFn: () => listUsers(listParams),
  });

  const users = useMemo(() => query.data?.users ?? [], [query.data]);
  const stats: UserStats = {
    total: query.data?.total ?? 0,
    active: query.data?.active ?? 0,
    inactive: query.data?.inactive ?? 0,
    admins: query.data?.admins ?? 0,
  };
  const loading = query.isLoading;
  const error = query.isError ? getApiErrorMessage(query.error, 'Failed to load users') : null;

  // Mutations invalidate the whole users domain on settle (#373 pattern).
  const invalidateUsers = useCallback(
    () => queryClient.invalidateQueries({ queryKey: queryKeys.users.all() }),
    [queryClient],
  );

  const createMutation = useMutation({
    mutationFn: (payload: CreateUserPayload) => createUser(payload),
    onSettled: () => invalidateUsers(),
  });
  const updateMutation = useMutation({
    mutationFn: ({ userId, payload }: { userId: number; payload: UpdateUserPayload }) =>
      updateUser(userId, payload),
    onSettled: () => invalidateUsers(),
  });
  const deleteMutation = useMutation({
    mutationFn: (userId: number) => deleteUser(userId),
    onSettled: () => invalidateUsers(),
  });
  const bulkDeleteMutation = useMutation({
    mutationFn: (userIds: number[]) => bulkDeleteUsers(userIds),
    onSettled: () => invalidateUsers(),
  });
  const toggleActiveMutation = useMutation({
    mutationFn: (userId: number) => toggleUserActive(userId),
    onSettled: () => invalidateUsers(),
  });

  // Sort handler
  const handleSort = useCallback((field: string) => {
    if (sortBy !== field) {
      setSortBy(field);
      setSortOrder('asc');
    } else if (sortOrder === 'asc') {
      setSortOrder('desc');
    } else {
      setSortBy(null);
      setSortOrder(null);
    }
  }, [sortBy, sortOrder]);

  // Selection handlers
  const toggleUserSelection = useCallback((userId: number) => {
    setSelectedUsers((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  }, []);

  const toggleAllUsers = useCallback(() => {
    setSelectedUsers((prev) =>
      prev.size === users.length ? new Set() : new Set(users.map((u) => u.id)),
    );
  }, [users]);

  // CRUD handlers
  const handleCreateUser = useCallback(
    async (form: UserFormData): Promise<boolean> => {
      if (!form.username || !form.password) {
        toast.error(t('common:errors.requiredField'));
        return false;
      }
      if (form.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email)) {
        toast.error(t('admin:users.messages.invalidEmail', 'Please enter a valid email address'));
        return false;
      }

      try {
        await createMutation.mutateAsync({
          username: form.username,
          password: form.password,
          role: form.role || 'user',
          email: form.email || undefined,
        });
        toast.success(t('users.messages.created'));
        return true;
      } catch (err) {
        handleApiError(err, t('users.messages.createFailed'));
        return false;
      }
    },
    [t, createMutation],
  );

  const handleUpdateUser = useCallback(
    async (userId: number, form: UserFormData, original: UserPublic): Promise<boolean> => {
      try {
        const updateData: UpdateUserPayload = {};
        if (form.username !== original.username) updateData.username = form.username;
        if (form.email !== (original.email ?? '')) updateData.email = form.email || null;
        if (form.role !== original.role) updateData.role = form.role;
        if (form.is_active !== original.is_active) updateData.is_active = form.is_active;
        if (form.password) updateData.password = form.password;

        await updateMutation.mutateAsync({ userId, payload: updateData });
        toast.success(t('users.messages.updated'));
        return true;
      } catch (err) {
        handleApiError(err, t('users.messages.updateFailed'));
        return false;
      }
    },
    [t, updateMutation],
  );

  const handleDeleteUser = useCallback(
    async (userId: number) => {
      const confirmed = await confirm(t('users.deleteConfirmGeneric'), {
        title: t('users.deleteUser'),
        variant: 'danger',
        confirmLabel: t('common:buttons.delete'),
      });
      if (!confirmed) return;

      try {
        await deleteMutation.mutateAsync(userId);
        toast.success(t('users.messages.deleted'));
      } catch (err) {
        handleApiError(err, t('users.messages.deleteFailed'));
      }
    },
    [t, confirm, deleteMutation],
  );

  const handleBulkDelete = useCallback(async () => {
    if (selectedUsers.size === 0) return;

    try {
      const result = await bulkDeleteMutation.mutateAsync(Array.from(selectedUsers));
      toast.success(t('users.bulk.deleted', { count: result.deleted }));
      setSelectedUsers(new Set());
    } catch (err) {
      handleApiError(err, t('users.messages.bulkDeleteFailed'));
    }
  }, [selectedUsers, t, bulkDeleteMutation]);

  const handleToggleActive = useCallback(
    async (userId: number) => {
      try {
        await toggleActiveMutation.mutateAsync(userId);
        toast.success(t('users.messages.statusUpdated'));
      } catch (err) {
        handleApiError(err, t('users.messages.toggleFailed'));
      }
    },
    [t, toggleActiveMutation],
  );

  const handleExportCSV = useCallback(() => {
    const headers = ['Username', 'Email', 'Role', 'Status', 'Created At'];
    const rows = users.map((u) => [
      u.username,
      u.email,
      u.role,
      u.is_active ? 'Active' : 'Inactive',
      new Date(u.created_at).toLocaleDateString(),
    ]);

    const csv = [headers.join(','), ...rows.map((row) => row.join(','))].join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `users-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
    toast.success(t('users.messages.exported'));
  }, [users, t]);

  return {
    // Data
    users,
    stats,
    loading,
    error,

    // Filters
    searchTerm,
    setSearchTerm,
    roleFilter,
    setRoleFilter,
    statusFilter,
    setStatusFilter,
    sortBy,
    sortOrder,
    handleSort,

    // Selection
    selectedUsers,
    toggleUserSelection,
    toggleAllUsers,

    // CRUD
    handleCreateUser,
    handleUpdateUser,
    handleDeleteUser,
    handleBulkDelete,
    handleToggleActive,
    handleExportCSV,

    // Confirm dialog
    confirmDialog: confirmDialog as ReactNode,
  };
}
