import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { buildApiUrl } from '../lib/api';
import { 
  Search, 
  ArrowUpDown, 
  Trash2,
  Edit,
  Plus,
  CheckCircle,
  XCircle,
  Download,
  Users,
  Shield,
  X
} from 'lucide-react';

interface User {
  id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

interface UserStats {
  total: number;
  active: number;
  inactive: number;
  admins: number;
}

interface UserFormData {
  username: string;
  email: string;
  password: string;
  role: string;
  is_active: boolean;
}

export default function UserManagement() {
  const [users, setUsers] = useState<User[]>([]);
  const [stats, setStats] = useState<UserStats>({ total: 0, active: 0, inactive: 0, admins: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Filter & Search
  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  
  // Selection & Bulk Actions
  const [selectedUsers, setSelectedUsers] = useState<Set<string>>(new Set());
  
  // Modal States
  const [showUserModal, setShowUserModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [userToDelete, setUserToDelete] = useState<string | null>(null);
  
  // Form Data
  const [formData, setFormData] = useState<UserFormData>({
    username: '',
    email: '',
    password: '',
    role: 'user',
    is_active: true
  });

  useEffect(() => {
    loadUsers();
  }, [searchTerm, roleFilter, statusFilter, sortBy, sortOrder]);

  const loadUsers = async () => {
    setLoading(true);
    setError(null);
    const token = localStorage.getItem('token');
    
    if (!token) {
      const errorMsg = 'No authentication token found. Please log in.';
      setError(errorMsg);
      toast.error(errorMsg);
      setLoading(false);
      return;
    }

    try {
      const params = new URLSearchParams();
      if (searchTerm) params.append('search', searchTerm);
      if (roleFilter) params.append('role', roleFilter);
      if (statusFilter) params.append('is_active', statusFilter);
      params.append('sort_by', sortBy);
      params.append('sort_order', sortOrder);

      const url = buildApiUrl(`/api/users/?${params.toString()}`);
      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        const errorMsg = errorData.detail || errorData.error || `HTTP ${response.status}: Failed to load users`;
        setError(errorMsg);
        toast.error(errorMsg);
        setLoading(false);
        return;
      }

      const data = await response.json();
      
      if (data.users) {
        setUsers(data.users);
        setStats({
          total: data.total,
          active: data.active,
          inactive: data.inactive,
          admins: data.admins
        });
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to load users';
      console.error('Failed to load users:', err);
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateUser = async () => {
    const token = localStorage.getItem('token');
    if (!token) return;

    // Pflichtfelder validieren
    if (!formData.username || !formData.password) {
      toast.error('Bitte alle Pflichtfelder ausfüllen!');
      return;
    }
    // Email Format grob prüfen (nur wenn ausgefüllt)
    if (formData.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(formData.email)) {
      toast.error('Bitte eine gültige E-Mail-Adresse eingeben!');
      return;
    }

    // Request-Body zusammenbauen
    const payload: any = {
      username: formData.username,
      password: formData.password,
      role: formData.role || 'user'
    };

    // Email nur hinzufügen wenn ausgefüllt
    if (formData.email) {
      payload.email = formData.email;
    }

    try {
      const response = await fetch(buildApiUrl('/api/users/'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errorData = await response.json();
        toast.error(errorData.detail || 'Failed to create user');
        return;
      }

      toast.success('User created successfully');
      setShowUserModal(false);
      resetForm();
      loadUsers();
    } catch (err) {
      toast.error('Failed to create user');
      console.error(err);
    }
  };

  const handleUpdateUser = async () => {
    if (!editingUser) return;
    const token = localStorage.getItem('token');
    if (!token) return;

    try {
      const updateData: any = {};
      if (formData.username !== editingUser.username) updateData.username = formData.username;
      if (formData.email !== editingUser.email) updateData.email = formData.email;
      if (formData.role !== editingUser.role) updateData.role = formData.role;
      if (formData.is_active !== editingUser.is_active) updateData.is_active = formData.is_active;
      if (formData.password) updateData.password = formData.password;

      const response = await fetch(buildApiUrl(`/api/users/${editingUser.id}`), {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(updateData)
      });

      if (!response.ok) {
        const errorData = await response.json();
        toast.error(errorData.detail || 'Failed to update user');
        return;
      }

      toast.success('User updated successfully');
      setShowUserModal(false);
      setEditingUser(null);
      resetForm();
      loadUsers();
    } catch (err) {
      toast.error('Failed to update user');
      console.error(err);
    }
  };

  const handleDeleteUser = async (userId: string) => {
    const token = localStorage.getItem('token');
    if (!token) return;

    try {
      const response = await fetch(buildApiUrl(`/api/users/${userId}`), {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        toast.error(errorData.detail || 'Failed to delete user');
        return;
      }

      toast.success('User deleted successfully');
      loadUsers();
    } catch (err) {
      toast.error('Failed to delete user');
      console.error(err);
    }
  };

  const handleBulkDelete = async () => {
    if (selectedUsers.size === 0) return;
    const token = localStorage.getItem('token');
    if (!token) return;

    try {
      const response = await fetch(buildApiUrl('/api/users/bulk-delete'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(Array.from(selectedUsers))
      });

      if (!response.ok) {
        toast.error('Failed to delete users');
        return;
      }

      const result = await response.json();
      toast.success(`Deleted ${result.deleted} user(s)`);
      setSelectedUsers(new Set());
      loadUsers();
    } catch (err) {
      toast.error('Failed to delete users');
      console.error(err);
    }
  };

  const handleToggleActive = async (userId: string) => {
    const token = localStorage.getItem('token');
    if (!token) return;

    try {
      const response = await fetch(buildApiUrl(`/api/users/${userId}/toggle-active`), {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      });

      if (!response.ok) {
        toast.error('Failed to toggle user status');
        return;
      }

      toast.success('User status updated');
      loadUsers();
    } catch (err) {
      toast.error('Failed to toggle user status');
      console.error(err);
    }
  };

  const handleExportCSV = () => {
    const headers = ['Username', 'Email', 'Role', 'Status', 'Created At'];
    const rows = users.map(u => [
      u.username,
      u.email,
      u.role,
      u.is_active ? 'Active' : 'Inactive',
      new Date(u.created_at).toLocaleDateString()
    ]);

    const csv = [
      headers.join(','),
      ...rows.map(row => row.join(','))
    ].join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `users-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
    toast.success('Users exported to CSV');
  };

  const openCreateModal = () => {
    resetForm();
    setEditingUser(null);
    setShowUserModal(true);
  };

  const openEditModal = (user: User) => {
    setFormData({
      username: user.username,
      email: user.email,
      password: '',
      role: user.role,
      is_active: user.is_active
    });
    setEditingUser(user);
    setShowUserModal(true);
  };

  const openDeleteConfirm = (userId: string) => {
    setUserToDelete(userId);
    setShowDeleteConfirm(true);
  };

  const confirmDelete = () => {
    if (userToDelete) {
      handleDeleteUser(userToDelete);
      setShowDeleteConfirm(false);
      setUserToDelete(null);
    }
  };

  const resetForm = () => {
    setFormData({
      username: '',
      email: '',
      password: '',
      role: 'user',
      is_active: true
    });
  };

  const toggleUserSelection = (userId: string) => {
    const newSelection = new Set(selectedUsers);
    if (newSelection.has(userId)) {
      newSelection.delete(userId);
    } else {
      newSelection.add(userId);
    }
    setSelectedUsers(newSelection);
  };

  const toggleAllUsers = () => {
    if (selectedUsers.size === users.length) {
      setSelectedUsers(new Set());
    } else {
      setSelectedUsers(new Set(users.map(u => u.id)));
    }
  };

  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('asc');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">
            User Management
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">Control access policies and collaboration roles</p>
        </div>
        <div className="flex gap-2">
          <button 
            onClick={handleExportCSV}
            className="btn btn-secondary flex items-center gap-2 flex-1 sm:flex-initial justify-center touch-manipulation active:scale-95"
          >
            <Download className="h-4 w-4" />
            <span className="hidden sm:inline">Export CSV</span>
            <span className="sm:hidden">Export</span>
          </button>
          <button 
            onClick={openCreateModal}
            className="btn btn-primary flex items-center gap-2 flex-1 sm:flex-initial justify-center touch-manipulation active:scale-95"
          >
            <Plus className="h-4 w-4" />
            <span className="hidden sm:inline">Add User</span>
            <span className="sm:hidden">Add</span>
          </button>
        </div>
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs sm:text-sm text-slate-400 truncate">Total Users</p>
              <p className="mt-1 text-xl sm:text-2xl font-semibold text-white">{stats.total}</p>
            </div>
            <Users className="h-6 w-6 sm:h-8 sm:w-8 text-sky-500 flex-shrink-0 ml-2" />
          </div>
        </div>
        
        <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs sm:text-sm text-slate-400 truncate">Active</p>
              <p className="mt-1 text-xl sm:text-2xl font-semibold text-green-400">{stats.active}</p>
            </div>
            <CheckCircle className="h-6 w-6 sm:h-8 sm:w-8 text-green-500 flex-shrink-0 ml-2" />
          </div>
        </div>
        
        <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs sm:text-sm text-slate-400 truncate">Inactive</p>
              <p className="mt-1 text-xl sm:text-2xl font-semibold text-slate-400">{stats.inactive}</p>
            </div>
            <XCircle className="h-6 w-6 sm:h-8 sm:w-8 text-slate-500 flex-shrink-0 ml-2" />
          </div>
        </div>
        
        <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs sm:text-sm text-slate-400 truncate">Admins</p>
              <p className="mt-1 text-xl sm:text-2xl font-semibold text-sky-400">{stats.admins}</p>
            </div>
            <Shield className="h-6 w-6 sm:h-8 sm:w-8 text-sky-500 flex-shrink-0 ml-2" />
          </div>
        </div>
      </div>

      {/* Filters and Search */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
        <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
          <div className="flex-1 min-w-0">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search users..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900/70 py-2 pl-10 pr-4 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
            </div>
          </div>
          
          <div className="flex gap-2">
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="flex-1 sm:flex-initial rounded-lg border border-slate-700 bg-slate-900/70 px-3 sm:px-4 py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="">All Roles</option>
              <option value="admin">Admin</option>
              <option value="user">User</option>
            </select>
            
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="flex-1 sm:flex-initial rounded-lg border border-slate-700 bg-slate-900/70 px-3 sm:px-4 py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="">All Status</option>
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </select>
          </div>
        </div>

        {selectedUsers.size > 0 && (
          <div className="mt-4 flex items-center justify-between rounded-lg border border-rose-900/60 bg-rose-950/30 p-3">
            <span className="text-sm text-rose-200">
              {selectedUsers.size} user(s) selected
            </span>
            <button
              onClick={handleBulkDelete}
              className="flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
            >
              <Trash2 className="h-4 w-4" />
              Delete Selected
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="card border-red-900/60 bg-red-950/30 p-4">
          <p className="text-sm text-red-400">
            <strong>Error:</strong> {error}
          </p>
        </div>
      )}

      {/* Desktop Users Table */}
      {loading ? (
        <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center">
          <p className="text-sm text-slate-500">Loading users...</p>
        </div>
      ) : (
        <div className="hidden lg:block card border-slate-800/60 bg-slate-900/55">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-800/60">
              <thead>
                <tr className="text-left text-xs uppercase tracking-[0.25em] text-slate-500">
                  <th className="px-6 py-4">
                    <input
                      type="checkbox"
                      checked={selectedUsers.size === users.length && users.length > 0}
                      onChange={toggleAllUsers}
                      className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-sky-500"
                    />
                  </th>
                  <th className="px-6 py-4">
                    <button 
                      onClick={() => handleSort('username')}
                      className="flex items-center gap-1 hover:text-slate-300"
                    >
                      Username
                      {sortBy === 'username' && <ArrowUpDown className="h-3 w-3" />}
                    </button>
                  </th>
                  <th className="px-6 py-4">Email</th>
                  <th className="px-6 py-4">
                    <button 
                      onClick={() => handleSort('role')}
                      className="flex items-center gap-1 hover:text-slate-300"
                    >
                      Role
                      {sortBy === 'role' && <ArrowUpDown className="h-3 w-3" />}
                    </button>
                  </th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4">
                    <button 
                      onClick={() => handleSort('created_at')}
                      className="flex items-center gap-1 hover:text-slate-300"
                    >
                      Created
                      {sortBy === 'created_at' && <ArrowUpDown className="h-3 w-3" />}
                    </button>
                  </th>
                  <th className="px-6 py-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-500">
                      No users found
                    </td>
                  </tr>
                ) : (
                  users.map((user) => (
                    <tr key={user.id} className="group transition hover:bg-slate-900/70">
                      <td className="px-6 py-4">
                        <input
                          type="checkbox"
                          checked={selectedUsers.has(user.id)}
                          onChange={() => toggleUserSelection(user.id)}
                          className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-sky-500"
                        />
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-200">
                        <div className="flex items-center gap-3">
                          <span className="flex h-9 w-9 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/70 text-sm font-semibold text-slate-300">
                            {user.username.charAt(0).toUpperCase()}
                          </span>
                          <span className="font-medium group-hover:text-white">{user.username}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-400">
                        {user.email}
                      </td>
                      <td className="px-6 py-4">
                        <span className={`rounded-full px-3 py-1 text-xs font-medium ${
                          user.role === 'admin'
                            ? 'border border-sky-500/40 bg-sky-500/15 text-sky-200'
                            : 'border border-slate-700/70 bg-slate-900/70 text-slate-300'
                        }`}>
                          {user.role}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <button
                          onClick={() => handleToggleActive(user.id)}
                          className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium transition ${
                            user.is_active
                              ? 'border border-green-500/40 bg-green-500/15 text-green-200 hover:bg-green-500/25'
                              : 'border border-slate-700/70 bg-slate-900/70 text-slate-400 hover:bg-slate-800/70'
                          }`}
                        >
                          {user.is_active ? (
                            <>
                              <CheckCircle className="h-3 w-3" />
                              Active
                            </>
                          ) : (
                            <>
                              <XCircle className="h-3 w-3" />
                              Inactive
                            </>
                          )}
                        </button>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-400">
                        {new Date(user.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 text-sm">
                        <div className="flex items-center gap-2">
                          <button 
                            onClick={() => openEditModal(user)}
                            className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-2 text-sky-200 transition hover:border-sky-500/50 hover:bg-sky-500/20"
                            title="Edit user"
                          >
                            <Edit className="h-4 w-4" />
                          </button>
                          <button 
                            onClick={() => openDeleteConfirm(user.id)}
                            className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
                            title="Delete user"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* User Create/Edit Modal */}
      {showUserModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-lg border border-slate-800 bg-slate-900 p-4 sm:p-6 shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="mb-3 sm:mb-4 flex items-center justify-between">
              <h2 className="text-lg sm:text-xl font-semibold text-white">
                {editingUser ? 'Edit User' : 'Create User'}
              </h2>
              <button
                onClick={() => {
                  setShowUserModal(false);
                  setEditingUser(null);
                  resetForm();
                }}
                className="rounded-lg p-2 hover:bg-slate-800 touch-manipulation active:scale-95"
              >
                <X className="h-5 w-5 text-slate-400" />
              </button>
            </div>

            <div className="space-y-3 sm:space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Username
                </label>
                <input
                  type="text"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  placeholder="Enter username"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Email <span className="text-slate-500">(optional)</span>
                </label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  placeholder="Enter email (optional)"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Password {editingUser && '(leave empty to keep current)'}
                </label>
                <input
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  placeholder="Enter password"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Role
                </label>
                <select
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                >
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                </select>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is_active"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-sky-500"
                />
                <label htmlFor="is_active" className="text-sm text-slate-300">
                  Active User
                </label>
              </div>
            </div>

            <div className="mt-4 sm:mt-6 flex gap-2">
              <button
                onClick={() => {
                  setShowUserModal(false);
                  setEditingUser(null);
                  resetForm();
                }}
                className="flex-1 rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 touch-manipulation active:scale-95"
              >
                Cancel
              </button>
              <button
                onClick={editingUser ? handleUpdateUser : handleCreateUser}
                className="flex-1 rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-200 hover:border-sky-500/50 hover:bg-sky-500/20 touch-manipulation active:scale-95"
              >
                {editingUser ? 'Update' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-lg border border-slate-800 bg-slate-900 p-4 sm:p-6 shadow-xl">
            <div className="mb-3 sm:mb-4 flex items-center gap-3">
              <div className="rounded-full bg-rose-500/20 p-2 sm:p-3">
                <Trash2 className="h-5 w-5 sm:h-6 sm:w-6 text-rose-500" />
              </div>
              <h2 className="text-lg sm:text-xl font-semibold text-white">Delete User</h2>
            </div>

            <p className="mb-4 sm:mb-6 text-sm text-slate-400">
              Are you sure you want to delete this user? This action cannot be undone.
            </p>

            <div className="flex gap-2">
              <button
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setUserToDelete(null);
                }}
                className="flex-1 rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 touch-manipulation active:scale-95"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                className="flex-1 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-sm font-medium text-rose-200 hover:border-rose-500/50 hover:bg-rose-500/20 touch-manipulation active:scale-95"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
