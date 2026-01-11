/**
 * Remote Server Profile Type Definition
 * Shared type for BaluDesk remote server profiles
 */

export interface RemoteServerProfile {
  id: number;
  name: string;
  sshHost: string;
  sshPort: number;
  sshUsername: string;
  sshPrivateKey?: string;
  vpnProfileId?: number;
  powerOnCommand?: string;
  lastUsed?: string;
  createdAt: string;
  updatedAt: string;
}
