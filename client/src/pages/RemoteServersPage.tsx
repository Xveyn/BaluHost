import { useServerProfiles, useVPNProfiles } from '@/hooks/useRemoteServers';
import { ServerProfileForm } from '@/components/RemoteServers/ServerProfileForm';
import { ServerProfileList } from '@/components/RemoteServers/ServerProfileList';
import { VPNProfileForm } from '@/components/RemoteServers/VPNProfileForm';
import { VPNProfileList } from '@/components/RemoteServers/VPNProfileList';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Server, Lock } from 'lucide-react';

export function RemoteServersPage() {
  const serverProfiles = useServerProfiles();
  const vpnProfiles = useVPNProfiles();

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Remote Servers</h1>
        <p className="text-muted-foreground mt-2">
          Manage and control your remote BaluHost servers with SSH and VPN profiles
        </p>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="servers" className="space-y-6">
        <TabsList>
          <TabsTrigger value="servers" className="flex items-center gap-2">
            <Server className="w-4 h-4" />
            Servers
          </TabsTrigger>
          <TabsTrigger value="vpn" className="flex items-center gap-2">
            <Lock className="w-4 h-4" />
            VPN Profiles
          </TabsTrigger>
        </TabsList>

        {/* Servers Tab */}
        <TabsContent value="servers" className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Server Profiles</CardTitle>
                  <CardDescription>
                    Add and manage remote BaluHost servers
                  </CardDescription>
                </div>
                <ServerProfileForm
                  vpnProfiles={vpnProfiles.profiles}
                  onCreateProfile={serverProfiles.createProfile}
                  isLoading={serverProfiles.loading}
                />
              </div>
            </CardHeader>
            <CardContent>
              <ServerProfileList
                profiles={serverProfiles.profiles}
                vpnProfiles={vpnProfiles.profiles}
                loading={serverProfiles.loading}
                onDelete={serverProfiles.deleteProfile}
                onTestConnection={serverProfiles.testConnection}
                onStartServer={serverProfiles.startServer}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* VPN Tab */}
        <TabsContent value="vpn" className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>VPN Profiles</CardTitle>
                  <CardDescription>
                    Upload and manage VPN configurations for secure connections
                  </CardDescription>
                </div>
                <VPNProfileForm
                  onCreateProfile={vpnProfiles.createProfile}
                  isLoading={vpnProfiles.loading}
                />
              </div>
            </CardHeader>
            <CardContent>
              <VPNProfileList
                profiles={vpnProfiles.profiles}
                loading={vpnProfiles.loading}
                onDelete={vpnProfiles.deleteProfile}
                onTestConnection={vpnProfiles.testConnection}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Info Card */}
      <Card className="bg-blue-50 border-blue-200">
        <CardHeader>
          <CardTitle className="text-blue-900">Quick Start</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-blue-800 space-y-2">
          <p>1. Create a VPN Profile if you need secure access (optional)</p>
          <p>2. Add a Server Profile with your SSH credentials</p>
          <p>3. Test the connection to verify SSH access</p>
          <p>4. Use "Start Server" to remotely power on your server</p>
        </CardContent>
      </Card>
    </div>
  );
}
