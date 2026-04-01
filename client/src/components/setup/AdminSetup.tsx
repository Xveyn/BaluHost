import { useState } from 'react';
import toast from 'react-hot-toast';
import { Eye, EyeOff, Shield } from 'lucide-react';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { createSetupAdmin } from '../../api/setup';
import { handleApiError } from '../../lib/errorHandling';

export interface AdminSetupProps {
  onComplete: (token: string) => void;
}

function getPasswordStrength(password: string): { score: number; label: string; color: string } {
  if (!password) return { score: 0, label: '', color: 'bg-slate-700' };

  let score = 0;
  if (password.length >= 8) score++;
  if (password.length >= 12) score++;
  if (/[A-Z]/.test(password)) score++;
  if (/[0-9]/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;

  if (score <= 1) return { score, label: 'Sehr schwach', color: 'bg-red-600' };
  if (score === 2) return { score, label: 'Schwach', color: 'bg-orange-500' };
  if (score === 3) return { score, label: 'Mittel', color: 'bg-yellow-500' };
  if (score === 4) return { score, label: 'Stark', color: 'bg-sky-500' };
  return { score, label: 'Sehr stark', color: 'bg-green-500' };
}

export function AdminSetup({ onComplete }: AdminSetupProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [email, setEmail] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const strength = getPasswordStrength(password);

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
    } else if (!/[A-Z]/.test(password)) {
      newErrors.password = 'Passwort muss mindestens einen Großbuchstaben enthalten';
    } else if (!/[0-9]/.test(password)) {
      newErrors.password = 'Passwort muss mindestens eine Zahl enthalten';
    }

    if (password !== confirmPassword) {
      newErrors.confirmPassword = 'Passwörter stimmen nicht überein';
    }

    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      newErrors.email = 'Ungültige E-Mail-Adresse';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setLoading(true);
    try {
      const result = await createSetupAdmin({
        username: username.trim(),
        password,
        email: email.trim() || undefined,
      });
      toast.success(`Admin-Konto "${result.username}" erstellt`);
      onComplete(result.setup_token);
    } catch (err) {
      handleApiError(err, 'Fehler beim Erstellen des Admin-Kontos');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-sky-500/20 flex items-center justify-center">
          <Shield className="w-5 h-5 text-sky-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Administrator-Konto erstellen</h2>
          <p className="text-sm text-slate-400">
            Dies wird das Hauptverwaltungskonto Ihres NAS-Systems sein.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Benutzername"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="z. B. admin"
          error={errors.username}
          autoComplete="username"
          autoFocus
        />

        <div className="space-y-1">
          <div className="relative">
            <Input
              label="Passwort"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Sicheres Passwort"
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

          {password && (
            <div className="mt-2 space-y-1">
              <div className="flex gap-1 h-1">
                {[1, 2, 3, 4, 5].map((level) => (
                  <div
                    key={level}
                    className={`flex-1 rounded-full transition-all ${
                      strength.score >= level ? strength.color : 'bg-slate-700'
                    }`}
                  />
                ))}
              </div>
              <p className="text-xs text-slate-400">
                Passwortstärke: <span className="text-slate-200">{strength.label}</span>
              </p>
            </div>
          )}
        </div>

        <div className="relative">
          <Input
            label="Passwort bestätigen"
            type={showConfirm ? 'text' : 'password'}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Passwort wiederholen"
            error={errors.confirmPassword}
            autoComplete="new-password"
            className="pr-10"
          />
          <button
            type="button"
            onClick={() => setShowConfirm((v) => !v)}
            className="absolute right-3 top-[38px] text-slate-400 hover:text-slate-200 transition-colors"
            tabIndex={-1}
          >
            {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>

        <Input
          label="E-Mail (optional)"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="admin@example.com"
          error={errors.email}
          autoComplete="email"
        />

        <div className="pt-4 flex justify-end">
          <Button type="submit" loading={loading} size="lg">
            Weiter
          </Button>
        </div>
      </form>
    </div>
  );
}
