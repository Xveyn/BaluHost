import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Plus, Loader2 } from 'lucide-react';
import * as api from '@/api/remote-servers';

interface VPNProfileFormProps {
  vpnProfiles: api.VPNProfile[];
  onCreateProfile: (formData: FormData) => Promise<api.VPNProfile>;
  isLoading?: boolean;
}

export function ServerProfileForm({ vpnProfiles, onCreateProfile, isLoading = false }: VPNProfileFormProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [sshHost, setSshHost] = useState('');
  const [sshPort, setSshPort] = useState('22');
  const [sshUsername, setSshUsername] = useState('root');
  const [sshKey, setSshKey] = useState('');
  const [vpnId, setVpnId] = useState<string>('');
  const [powerOnCommand, setPowerOnCommand] = useState('systemctl start baluhost-backend');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const data: api.ServerProfileCreate = {
        name,
        ssh_host: sshHost,
        ssh_port: parseInt(sshPort),
        ssh_username: sshUsername,
        ssh_private_key: sshKey,
        vpn_profile_id: vpnId ? parseInt(vpnId) : undefined,
        power_on_command: powerOnCommand || undefined,
      };

      await onCreateProfile(data);
      
      // Reset form
      setName('');
      setSshHost('');
      setSshPort('22');
      setSshUsername('root');
      setSshKey('');
      setVpnId('');
      setPowerOnCommand('systemctl start baluhost-backend');
      setOpen(false);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button><Plus className="w-4 h-4 mr-2" /> Add Server</Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add Server Profile</DialogTitle>
          <DialogDescription>
            Add SSH credentials to manage a remote BaluHost server
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Profile Name</Label>
            <Input
              id="name"
              placeholder="e.g., Home NAS"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-2 col-span-2">
              <Label htmlFor="host">SSH Host</Label>
              <Input
                id="host"
                placeholder="192.168.1.100"
                value={sshHost}
                onChange={(e) => setSshHost(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="port">Port</Label>
              <Input
                id="port"
                type="number"
                placeholder="22"
                value={sshPort}
                onChange={(e) => setSshPort(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="username">SSH Username</Label>
            <Input
              id="username"
              placeholder="root"
              value={sshUsername}
              onChange={(e) => setSshUsername(e.target.value)}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="key">SSH Private Key</Label>
            <Textarea
              id="key"
              placeholder="-----BEGIN PRIVATE KEY-----&#10;...&#10;-----END PRIVATE KEY-----"
              value={sshKey}
              onChange={(e) => setSshKey(e.target.value)}
              required
              className="font-mono text-xs"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="vpn">VPN Profile (Optional)</Label>
            <Select value={vpnId} onValueChange={setVpnId}>
              <SelectTrigger id="vpn">
                <SelectValue placeholder="None" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">None</SelectItem>
                {vpnProfiles.map((profile) => (
                  <SelectItem key={profile.id} value={profile.id.toString()}>
                    {profile.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="command">Power-On Command</Label>
            <Input
              id="command"
              placeholder="systemctl start baluhost-backend"
              value={powerOnCommand}
              onChange={(e) => setPowerOnCommand(e.target.value)}
            />
          </div>

          <Button type="submit" disabled={loading || isLoading} className="w-full">
            {loading || isLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
            Create Profile
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
