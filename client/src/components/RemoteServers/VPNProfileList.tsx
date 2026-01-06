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
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/components/ui/use-toast';
import {
  Trash2,
  CheckCircle,
  AlertCircle,
  Loader2,
  Shield,
  RefreshCw,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import * as api from '@/api/remote-servers';

interface VPNProfileListProps {
  profiles: api.VPNProfile[];
  loading: boolean;
  onDelete: (id: number) => Promise<void>;
  onTestConnection: (id: number) => Promise<api.VPNConnectionTest>;
}

export function VPNProfileList({
  profiles,
  loading,
  onDelete,
  onTestConnection,
}: VPNProfileListProps) {
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<Record<number, api.VPNConnectionTest>>({});
  const { toast } = useToast();

  const handleTest = async (id: number) => {
    setTestingId(id);
    try {
      const result = await onTestConnection(id);
      setConnectionStatus({ ...connectionStatus, [id]: result });
      toast({
        title: result.connected ? 'Valid' : 'Invalid',
        description: result.error_message || 'Configuration is valid',
        variant: result.connected ? 'default' : 'destructive',
      });
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = async () => {
    if (deleteId) {
      await onDelete(deleteId);
      setDeleteId(null);
    }
  };

  const getVpnTypeColor = (type: string) => {
    switch (type) {
      case 'openvpn':
        return 'bg-blue-100 text-blue-800';
      case 'wireguard':
        return 'bg-purple-100 text-purple-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2].map((i) => (
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
            No VPN profiles yet. Add one to connect to remote networks.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {profiles.map((profile) => {
        const status = connectionStatus[profile.id];
        const isValid = status?.connected;

        return (
          <Card key={profile.id}>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <CardTitle>{profile.name}</CardTitle>
                    <Badge className={getVpnTypeColor(profile.vpn_type)}>
                      {profile.vpn_type.toUpperCase()}
                    </Badge>
                    {profile.auto_connect && (
                      <Badge variant="secondary">
                        <Shield className="w-3 h-3 mr-1" />
                        Auto
                      </Badge>
                    )}
                  </div>
                  {profile.description && (
                    <CardDescription className="mt-2">{profile.description}</CardDescription>
                  )}
                </div>
                {isValid !== undefined && (
                  <div className="flex items-center gap-2">
                    {isValid ? (
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
                    <p className="text-muted-foreground">Created</p>
                    <p className="font-medium">
                      {formatDistanceToNow(new Date(profile.created_at), { addSuffix: true })}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Last Updated</p>
                    <p className="font-medium">
                      {formatDistanceToNow(new Date(profile.updated_at), { addSuffix: true })}
                    </p>
                  </div>
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
                      <RefreshCw className="w-4 h-4 mr-2" />
                    )}
                    Validate Config
                  </Button>

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
            <AlertDialogTitle>Delete VPN Profile?</AlertDialogTitle>
            <AlertDialogDescription>
              This will remove the VPN profile and any server profiles using it will have the VPN reference cleared.
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
