import { AuthUser } from '../types/index.js';

const privilegedRoles = (process.env.PRIVILEGED_ROLES || 'admin')
  .split(',')
  .map((role) => role.trim())
  .filter(Boolean);

export const isPrivileged = (user: AuthUser | undefined): boolean => {
  if (!user) {
    return false;
  }
  return privilegedRoles.includes(user.role);
};

export class PermissionDeniedError extends Error {
  constructor(message = 'Operation not permitted') {
    super(message);
    this.name = 'PermissionDeniedError';
  }
}

export const ensureOwnerOrPrivileged = (user: AuthUser | undefined, ownerId?: string | null): void => {
  if (!user) {
    throw new PermissionDeniedError('Authentication required');
  }
  if (!ownerId) {
    if (!isPrivileged(user)) {
      throw new PermissionDeniedError();
    }
    return;
  }
  if (ownerId === user.id) {
    return;
  }
  if (!isPrivileged(user)) {
    throw new PermissionDeniedError();
  }
};

export const canAccess = (user: AuthUser | undefined, ownerId?: string | null): boolean => {
  if (!user) {
    return false;
  }
  if (!ownerId) {
    return true;
  }
  if (ownerId === user.id) {
    return true;
  }
  return isPrivileged(user);
};
