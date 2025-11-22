import { useState, useEffect } from 'react';
import { buildApiUrl } from '../lib/api';

interface User {
  id: string;
  username: string;
  email: string;
  role: string;
}

export default function UserManagement() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    setLoading(true);
    const token = localStorage.getItem('token');

    try {
      const response = await fetch(buildApiUrl('/api/users'), {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      const data = await response.json();
      if (data.users) {
        setUsers(data.users);
      }
    } catch (err) {
      console.error('Failed to load users:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-white">
            User Management
          </h1>
          <p className="mt-1 text-sm text-slate-400">Control access policies and collaboration roles</p>
        </div>
        <button className="btn btn-primary">
          + Add User
        </button>
      </div>

      {loading ? (
        <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center">
          <p className="text-sm text-slate-500">Loading users...</p>
        </div>
      ) : (
        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-800/60">
              <thead>
                <tr className="text-left text-xs uppercase tracking-[0.25em] text-slate-500">
                  <th className="px-6 py-4">Username</th>
                  <th className="px-6 py-4">Email</th>
                  <th className="px-6 py-4">Role</th>
                  <th className="px-6 py-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-6 py-12 text-center text-sm text-slate-500">
                      No users found
                    </td>
                  </tr>
                ) : (
                  users.map((user) => (
                    <tr key={user.id} className="group transition hover:bg-slate-900/70">
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
                      <td className="px-6 py-4 text-sm">
                        <div className="flex items-center gap-4">
                          <button className="text-sky-300 transition hover:text-sky-200">
                            Edit
                          </button>
                          <button className="text-rose-300 transition hover:text-rose-200">
                            Delete
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
    </div>
  );
}
