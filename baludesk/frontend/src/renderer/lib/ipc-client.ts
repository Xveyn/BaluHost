/**
 * IPC Client for communication with C++ backend via Electron IPC
 * Handles all Remote Server and VPN profile operations
 */

export interface RemoteServerProfile {
  id: number;
  name: string;
  sshHost: string;
  sshPort: number;
  sshUsername: string;
  sshPrivateKey?: string; // Not sent over IPC
  vpnProfileId?: number;
  powerOnCommand?: string;
  lastUsed?: string;
  createdAt: string;
  updatedAt: string;
}

export interface VPNProfile {
  id: number;
  name: string;
  vpnType: string; // openvpn, wireguard, etc
  description?: string;
  configContent?: string; // Not sent over IPC
  certificate?: string; // Not sent over IPC
  privateKey?: string; // Not sent over IPC
  autoConnect: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface ConnectionTestResult {
  connected: boolean;
  message: string;
}

class IPCClient {
  private requestId = 0;

  private sendMessage(message: any): Promise<any> {
    return new Promise((resolve, reject) => {
      const id = ++this.requestId;
      
      const handleResponse = (event: any, response: any) => {
        if (response.requestId === id) {
          window.electronAPI?.removeIPCListener?.(handleResponse);
          
          if (response.success) {
            resolve(response.data);
          } else {
            reject(new Error(response.error || 'IPC request failed'));
          }
        }
      };

      window.electronAPI?.onIPCMessage?.(handleResponse);
      
      const msg = { ...message, requestId: id };
      window.electronAPI?.sendIPCMessage?.(msg);

      // Timeout after 30 seconds
      setTimeout(() => {
        window.electronAPI?.removeIPCListener?.(handleResponse);
        reject(new Error('IPC request timeout'));
      }, 30000);
    });
  }

  // Remote Server Profile operations
  async addRemoteServerProfile(profile: Omit<RemoteServerProfile, 'id' | 'createdAt' | 'updatedAt'>) {
    return this.sendMessage({
      type: 'add_remote_server_profile',
      name: profile.name,
      sshHost: profile.sshHost,
      sshPort: profile.sshPort,
      sshUsername: profile.sshUsername,
      sshPrivateKey: profile.sshPrivateKey,
      vpnProfileId: profile.vpnProfileId,
      powerOnCommand: profile.powerOnCommand,
    });
  }

  async updateRemoteServerProfile(profile: RemoteServerProfile) {
    return this.sendMessage({
      type: 'update_remote_server_profile',
      id: profile.id,
      name: profile.name,
      sshHost: profile.sshHost,
      sshPort: profile.sshPort,
      sshUsername: profile.sshUsername,
      sshPrivateKey: profile.sshPrivateKey,
      vpnProfileId: profile.vpnProfileId,
      powerOnCommand: profile.powerOnCommand,
    });
  }

  async deleteRemoteServerProfile(id: number) {
    return this.sendMessage({
      type: 'delete_remote_server_profile',
      id,
    });
  }

  async getRemoteServerProfile(id: number): Promise<RemoteServerProfile> {
    return this.sendMessage({
      type: 'get_remote_server_profile',
      id,
    });
  }

  async getRemoteServerProfiles(): Promise<RemoteServerProfile[]> {
    return this.sendMessage({
      type: 'get_remote_server_profiles',
    });
  }

  async testServerConnection(id: number): Promise<ConnectionTestResult> {
    return this.sendMessage({
      type: 'test_server_connection',
      id,
    });
  }

  async startRemoteServer(id: number) {
    return this.sendMessage({
      type: 'start_remote_server',
      id,
    });
  }

  // VPN Profile operations
  async addVPNProfile(profile: Omit<VPNProfile, 'id' | 'createdAt' | 'updatedAt'>) {
    return this.sendMessage({
      type: 'add_vpn_profile',
      name: profile.name,
      vpnType: profile.vpnType,
      description: profile.description,
      configContent: profile.configContent,
      certificate: profile.certificate,
      privateKey: profile.privateKey,
      autoConnect: profile.autoConnect,
    });
  }

  async updateVPNProfile(profile: VPNProfile) {
    return this.sendMessage({
      type: 'update_vpn_profile',
      id: profile.id,
      name: profile.name,
      vpnType: profile.vpnType,
      description: profile.description,
      configContent: profile.configContent,
      certificate: profile.certificate,
      privateKey: profile.privateKey,
      autoConnect: profile.autoConnect,
    });
  }

  async deleteVPNProfile(id: number) {
    return this.sendMessage({
      type: 'delete_vpn_profile',
      id,
    });
  }

  async getVPNProfile(id: number): Promise<VPNProfile> {
    return this.sendMessage({
      type: 'get_vpn_profile',
      id,
    });
  }

  async getVPNProfiles(): Promise<VPNProfile[]> {
    return this.sendMessage({
      type: 'get_vpn_profiles',
    });
  }

  async testVPNConnection(id: number): Promise<ConnectionTestResult> {
    return this.sendMessage({
      type: 'test_vpn_connection',
      id,
    });
  }
}

export const ipcClient = new IPCClient();
