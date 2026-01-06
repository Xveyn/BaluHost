import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/components/ui/use-toast';
import {
  Power,
  Trash2,
  Network,
  Loader2,
  CheckCircle,
  AlertCircle,
  Clock,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import * as api from '@/api/remote-servers';

interface ServerProfileListProps {
  profiles: api.ServerProfile[];
  vpnProfiles: api.VPNProfile[];
  loading: boolean;
  onDelete: (id: number) => Promise<void>;
  onTestConnection: (id: number) => Promise<api.SSHConnectionTest>;
  onStartServer: (id: number) => Promise<api.ServerStartResponse>;
}

export function ServerProfileList({
  profiles,
  vpnProfiles,
  loading,
  onDelete,
  onTestConnection,
  onStartServer,
}: ServerProfileListProps) {
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [startingId, setStartingId] = useState<number | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<Record<number, api.SSHConnectionTest>>({});
  const { toast } = useToast();

  const handleTest = async (id: number) => {
    setTestingId(id);
    try {
      const result = await onTestConnection(id);
      setConnectionStatus({ ...connectionStatus, [id]: result });
      toast({
        title: result.ssh_reachable ? 'Connected' : 'Disconnected',
        description: result.error_message || 'SSH connection successful',
        variant: result.ssh_reachable ? 'default' : 'destructive',
      });
    } finally {
      setTestingId(null);
    }
  };

  const handleStart = async (id: number) => {
    setStartingId(id);
    try {
      const result = await onStartServer(id);
      if (result.status === 'starting') {
        toast({
          title: 'Server Starting',
          description: 'Check the server status in a few moments',
        });
      }
    } finally {
      setStartingId(null);
    }
  };

  const handleDelete = async () => {
    if (deleteId) {
      await onDelete(deleteId);
      setDeleteId(null);
    }
  };

  const getVpnName = (vpnId?: number) => {
    if (!vpnId) return 'None';
    return vpnProfiles.find(p => p.id === vpnId)?.name || 'Unknown';
  };

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-4 w-64 mt-2" />
            </CardHeader>
          </Card>
        ))}
      </div>
    );
  }

  if (profiles.length === 0) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-center text-muted-foreground">
            No server profiles yet. Add one to get started.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {profiles.map((profile) => {
        const status = connectionStatus[profile.id];
        const isConnected = status?.ssh_reachable;
        
        return (
          <Card key={profile.id}>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle>{profile.name}</CardTitle>
                  <CardDescription>
                    {profile.ssh_username}@{profile.ssh_host}:{profile.ssh_port}
                  </CardDescription>
                </div>
                {isConnected !== undefined && (
                  <div className="flex items-center gap-2">
                    {isConnected ? (
                      <CheckCircle className="w-5 h-5 text-green-500" />
                    ) : (
                      <AlertCircle className="w-5 h-5 text-red-500" />
                    )}
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {/* Details */}
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">VPN Profile</p>
                    <p className="font-medium">{getVpnName(profile.vpn_profile_id)}</p>
                  </div>
                  {profile.power_on_command && (
                    <div>
                      <p className="text-muted-foreground">Power-On Command</p>
                      <p className="font-mono text-xs">{profile.power_on_command}</p>
                    </div>
                  )}
                  {profile.last_used && (
                    <div>
                      <p className="text-muted-foreground">Last Used</p>
                      <p className="font-medium flex items-center gap-1">
                        <Clock className="w-4 h-4" />
                        {formatDistanceToNow(new Date(profile.last_used), { addSuffix: true })}
                      </p>
                    </div>
                  )}
                </div>

                {/* Error message */}
                {status?.error_message && (
                  <div className="bg-destructive/10 text-destructive p-2 rounded text-sm">
                    {status.error_message}
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleTest(profile.id)}
                    disabled={testingId === profile.id}
                  >
                    {testingId === profile.id ? (
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <Network className="w-4 h-4 mr-2" />
                    )}
                    Test Connection
                  </Button>

                  {profile.power_on_command && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleStart(profile.id)}
                      disabled={startingId === profile.id}
                      className="text-green-600 hover:text-green-700"
                    >
                      {startingId === profile.id ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      ) : (
                        <Power className="w-4 h-4 mr-2" />
                      )}
                      Start Server
                    </Button>
                  )}

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeleteId(profile.id)}
                    className="text-destructive hover:text-destructive ml-auto"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}

      <AlertDialog open={deleteId !== null} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Profile?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the profile. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex gap-2 justify-end">
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive hover:bg-destructive/90">
              Delete
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
