import { useState } from 'react';
import toast from 'react-hot-toast';
import { Users, Plus, Trash2, Eye, EyeOff } from 'lucide-react';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { createSetupUser, deleteSetupUser, type SetupUserResponse } from '../../api/setup';
import { handleApiError } from '../../lib/errorHandling';

export interface UserSetupProps {
  setupToken: string;
  onComplete: () => void;
}

interface CreatedUser extends SetupUserResponse {
  user_id: number;
}

export function UserSetup({ setupToken, onComplete }: UserSetupProps) {
  const [users, setUsers] = useState<CreatedUser[]>([]);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!username.trim()) {
      newErrors.username = 'Benutzername ist erforderlich';
    } else if (username.length < 3) {
      newErrors.username = 'Benutzername muss mindestens 3 Zeichen lang sein';
    }

    if (!password) {
      newErrors.password = 'Passwort ist erforderlich';
    } else if (password.length < 8) {
      newErrors.password = 'Passwort muss mindestens 8 Zeichen lang sein';
    }

    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      newErrors.email = 'Ungültige E-Mail-Adresse';
    }

    if (users.some((u) => u.username.toLowerCase() === username.trim().toLowerCase())) {
      newErrors.username = 'Dieser Benutzername wurde bereits hinzugefügt';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setLoading(true);
    try {
      const result = await createSetupUser(
        {
          username: username.trim(),
          password,
          email: email.trim() || undefined,
        },
        setupToken
      );
      setUsers((prev) => [...prev, result as CreatedUser]);
      toast.success(`Benutzer "${result.username}" hinzugefügt`);
      setUsername('');
      setPassword('');
      setEmail('');
      setErrors({});
    } catch (err) {
      handleApiError(err, 'Fehler beim Erstellen des Benutzers');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteUser = async (userId: number, uname: string) => {
    setDeletingId(userId);
    try {
      await deleteSetupUser(userId, setupToken);
      setUsers((prev) => prev.filter((u) => u.user_id !== userId));
      toast.success(`Benutzer "${uname}" entfernt`);
    } catch (err) {
      handleApiError(err, 'Fehler beim Löschen des Benutzers');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-sky-500/20 flex items-center justify-center">
          <Users className="w-5 h-5 text-sky-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Benutzer anlegen</h2>
          <p className="text-sm text-slate-400">
            Erstellen Sie mindestens einen regulären Benutzer für Ihr NAS-System.
          </p>
        </div>
      </div>

      {/* Created users list */}
      {users.length > 0 && (
        <div className="mb-5 space-y-2">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
            Angelegte Benutzer ({users.length})
          </p>
          {users.map((user) => (
            <div
              key={user.user_id}
              className="flex items-center justify-between px-4 py-3 bg-slate-800/40 rounded-lg border border-slate-700"
            >
              <div>
                <span className="text-sm font-medium text-slate-100">{user.username}</span>
                {user.email && (
                  <span className="ml-2 text-xs text-slate-400">{user.email}</span>
                )}
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleDeleteUser(user.user_id, user.username)}
                loading={deletingId === user.user_id}
                className="text-red-400 hover:text-red-300 hover:bg-red-900/20"
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Add user form */}
      <form onSubmit={handleAddUser} className="space-y-4">
        <p className="text-sm font-medium text-slate-300">
          {users.length === 0 ? 'Benutzer hinzufügen' : 'Weiteren Benutzer hinzufügen'}
        </p>

        <Input
          label="Benutzername"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="z. B. johndoe"
          error={errors.username}
          autoComplete="off"
        />

        <div className="relative">
          <Input
            label="Passwort"
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Passwort"
            error={errors.password}
            autoComplete="new-password"
            className="pr-10"
          />
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            className="absolute right-3 top-[38px] text-slate-400 hover:text-slate-200 transition-colors"
            tabIndex={-1}
          >
            {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>

        <Input
          label="E-Mail (optional)"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="benutzer@example.com"
          error={errors.email}
          autoComplete="off"
        />

        <Button
          type="submit"
          variant="secondary"
          loading={loading}
          icon={<Plus className="w-4 h-4" />}
        >
          Benutzer hinzufügen
        </Button>
      </form>

      <div className="mt-6 pt-4 border-t border-slate-700 flex justify-between items-center">
        <p className="text-sm text-slate-500">
          {users.length === 0
            ? 'Bitte mindestens einen Benutzer anlegen'
            : `${users.length} Benutzer angelegt`}
        </p>
        <Button
          onClick={onComplete}
          disabled={users.length === 0}
          size="lg"
        >
          Weiter
        </Button>
      </div>
    </div>
  );
}
