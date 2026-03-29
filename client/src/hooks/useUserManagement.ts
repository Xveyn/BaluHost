import { useState, useEffect, useRef, useCallback, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { handleApiError } from '../lib/errorHandling';
import { useConfirmDialog } from './useConfirmDialog';
import {
  listUsers,
  createUser,
  updateUser,
  deleteUser,
  bulkDeleteUsers,
  toggleUserActive,
  type UserPublic,
  type UsersResponse,
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

  // Data
  const [users, setUsers] = useState<UserPublic[]>([]);
  const [stats, setStats] = useState<UserStats>({ total: 0, active: 0, inactive: 0, admins: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  // Load users when filters change
  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const data: UsersResponse = await listUsers({
        search: debouncedSearch || undefined,
        role: roleFilter || undefined,
        is_active: statusFilter || undefined,
        sort_by: sortBy || undefined,
        sort_order: sortBy && sortOrder ? sortOrder : undefined,
      });

      setUsers(data.users);
      setStats({
        total: data.total,
        active: data.active,
        inactive: data.inactive,
        admins: data.admins,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load users';
      setError(message);
      handleApiError(err, 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch, roleFilter, statusFilter, sortBy, sortOrder]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

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
        await createUser({
          username: form.username,
          password: form.password,
          role: form.role || 'user',
          email: form.email || undefined,
        });
        toast.success(t('users.messages.created'));
        loadUsers();
        return true;
      } catch (err) {
        handleApiError(err, t('users.messages.createFailed'));
        return false;
      }
    },
    [t, loadUsers],
  );

  const handleUpdateUser = useCallback(
    async (userId: number, form: UserFormData, original: UserPublic): Promise<boolean> => {
      try {
        const updateData: Record<string, unknown> = {};
        if (form.username !== original.username) updateData.username = form.username;
        if (form.email !== (original.email ?? '')) updateData.email = form.email || null;
        if (form.role !== original.role) updateData.role = form.role;
        if (form.is_active !== original.is_active) updateData.is_active = form.is_active;
        if (form.password) updateData.password = form.password;

        await updateUser(userId, updateData);
        toast.success(t('users.messages.updated'));
        loadUsers();
        return true;
      } catch (err) {
        handleApiError(err, t('users.messages.updateFailed'));
        return false;
      }
    },
    [t, loadUsers],
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
        await deleteUser(userId);
        toast.success(t('users.messages.deleted'));
        loadUsers();
      } catch (err) {
        handleApiError(err, t('users.messages.deleteFailed'));
      }
    },
    [t, confirm, loadUsers],
  );

  const handleBulkDelete = useCallback(async () => {
    if (selectedUsers.size === 0) return;

    try {
      const result = await bulkDeleteUsers(Array.from(selectedUsers));
      toast.success(t('users.bulk.deleted', { count: result.deleted }));
      setSelectedUsers(new Set());
      loadUsers();
    } catch (err) {
      handleApiError(err, t('users.messages.bulkDeleteFailed'));
    }
  }, [selectedUsers, t, loadUsers]);

  const handleToggleActive = useCallback(
    async (userId: number) => {
      try {
        await toggleUserActive(userId);
        toast.success(t('users.messages.statusUpdated'));
        loadUsers();
      } catch (err) {
        handleApiError(err, t('users.messages.toggleFailed'));
      }
    },
    [t, loadUsers],
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
