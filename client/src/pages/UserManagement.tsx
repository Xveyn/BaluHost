import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, Plus } from 'lucide-react';
import { useUserManagement } from '../hooks/useUserManagement';
import type { UserFormData } from '../hooks/useUserManagement';
import type { UserPublic } from '../api/users';
import {
  UserStatsCards,
  UserFilters,
  UserTable,
  UserCardList,
  UserFormModal,
} from '../components/user-management';

export default function UserManagement() {
  const { t } = useTranslation(['admin', 'common']);
  const hook = useUserManagement();

  // Modal state (local — only UI concern)
  const [showModal, setShowModal] = useState(false);
  const [editingUser, setEditingUser] = useState<UserPublic | null>(null);

  const openCreate = () => { setEditingUser(null); setShowModal(true); };
  const openEdit = (user: UserPublic) => { setEditingUser(user); setShowModal(true); };
  const closeModal = () => { setShowModal(false); setEditingUser(null); };

  const handleSubmit = async (form: UserFormData, original: UserPublic | null): Promise<boolean> => {
    if (original) return hook.handleUpdateUser(original.id, form, original);
    return hook.handleCreateUser(form);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('users.title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">{t('users.subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={hook.handleExportCSV}
            className="btn btn-secondary flex items-center gap-2 flex-1 sm:flex-initial justify-center touch-manipulation active:scale-95"
          >
            <Download className="h-4 w-4" />
            <span className="hidden sm:inline">{t('users.buttons.exportCsv')}</span>
            <span className="sm:hidden">{t('users.buttons.export')}</span>
          </button>
          <button
            onClick={openCreate}
            className="btn btn-primary flex items-center gap-2 flex-1 sm:flex-initial justify-center touch-manipulation active:scale-95"
          >
            <Plus className="h-4 w-4" />
            <span className="hidden sm:inline">{t('users.buttons.addUser')}</span>
            <span className="sm:hidden">{t('users.buttons.add')}</span>
          </button>
        </div>
      </div>

      <UserStatsCards stats={hook.stats} />

      <UserFilters
        searchTerm={hook.searchTerm}
        onSearchChange={hook.setSearchTerm}
        roleFilter={hook.roleFilter}
        onRoleFilterChange={hook.setRoleFilter}
        statusFilter={hook.statusFilter}
        onStatusFilterChange={hook.setStatusFilter}
        selectedCount={hook.selectedUsers.size}
        onBulkDelete={hook.handleBulkDelete}
      />

      {hook.error && (
        <div className="card border-red-900/60 bg-red-950/30 p-4">
          <p className="text-sm text-red-400"><strong>Error:</strong> {hook.error}</p>
        </div>
      )}

      {hook.loading ? (
        <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center">
          <p className="text-sm text-slate-500">{t('users.loading')}</p>
        </div>
      ) : (
        <>
          <UserTable
            users={hook.users}
            selectedUsers={hook.selectedUsers}
            sortBy={hook.sortBy}
            sortOrder={hook.sortOrder}
            onSort={hook.handleSort}
            onToggleSelection={hook.toggleUserSelection}
            onToggleAll={hook.toggleAllUsers}
            onEdit={openEdit}
            onDelete={hook.handleDeleteUser}
            onToggleActive={hook.handleToggleActive}
          />
          <UserCardList
            users={hook.users}
            selectedUsers={hook.selectedUsers}
            onToggleSelection={hook.toggleUserSelection}
            onEdit={openEdit}
            onDelete={hook.handleDeleteUser}
            onToggleActive={hook.handleToggleActive}
          />
        </>
      )}

      <UserFormModal
        open={showModal}
        editingUser={editingUser}
        onClose={closeModal}
        onSubmit={handleSubmit}
      />

      {hook.confirmDialog}
    </div>
  );
}
