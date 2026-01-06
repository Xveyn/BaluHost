import { useState, useRef } from 'react';
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
import { Checkbox } from '@/components/ui/checkbox';
import { Plus, Upload, Loader2, X } from 'lucide-react';
import * as api from '@/api/remote-servers';

interface VPNProfileFormProps {
  onCreateProfile: (formData: FormData) => Promise<api.VPNProfile>;
  isLoading?: boolean;
}

export function VPNProfileForm({ onCreateProfile, isLoading = false }: VPNProfileFormProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [vpnType, setVpnType] = useState<'openvpn' | 'wireguard' | 'custom'>('openvpn');
  const [description, setDescription] = useState('');
  const [autoConnect, setAutoConnect] = useState(false);
  const [configFile, setConfigFile] = useState<File | null>(null);
  const [certFile, setCertFile] = useState<File | null>(null);
  const [keyFile, setKeyFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  const configInputRef = useRef<HTMLInputElement>(null);
  const certInputRef = useRef<HTMLInputElement>(null);
  const keyInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!configFile) return;

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('name', name);
      formData.append('vpn_type', vpnType);
      formData.append('description', description);
      formData.append('auto_connect', autoConnect.toString());
      formData.append('config_file', configFile);

      if (certFile) {
        formData.append('certificate_file', certFile);
      }
      if (keyFile) {
        formData.append('private_key_file', keyFile);
      }

      await onCreateProfile(formData);

      // Reset form
      setName('');
      setVpnType('openvpn');
      setDescription('');
      setAutoConnect(false);
      setConfigFile(null);
      setCertFile(null);
      setKeyFile(null);
      setOpen(false);
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (setter: (f: File | null) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setter(file);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button><Plus className="w-4 h-4 mr-2" /> Add VPN Profile</Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add VPN Profile</DialogTitle>
          <DialogDescription>
            Upload VPN configuration for secure remote access
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Profile Name</Label>
            <Input
              id="name"
              placeholder="e.g., Home OpenVPN"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="type">VPN Type</Label>
            <Select value={vpnType} onValueChange={(v) => setVpnType(v as any)}>
              <SelectTrigger id="type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="openvpn">OpenVPN</SelectItem>
                <SelectItem value="wireguard">WireGuard</SelectItem>
                <SelectItem value="custom">Custom</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Input
              id="description"
              placeholder="Optional description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {/* Config file upload */}
          <div className="space-y-2">
            <Label>Configuration File *</Label>
            <div
              onClick={() => configInputRef.current?.click()}
              className="border-2 border-dashed rounded-lg p-4 cursor-pointer hover:bg-muted transition-colors"
            >
              <div className="flex items-center justify-center gap-2">
                <Upload className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">
                  {configFile ? configFile.name : 'Click to upload config'}
                </span>
              </div>
              <input
                ref={configInputRef}
                type="file"
                hidden
                onChange={handleFileChange(setConfigFile)}
                accept=".ovpn,.conf"
              />
            </div>
          </div>

          {/* Certificate file upload */}
          <div className="space-y-2">
            <Label>Certificate (Optional)</Label>
            <div
              onClick={() => certInputRef.current?.click()}
              className="border-2 border-dashed rounded-lg p-4 cursor-pointer hover:bg-muted transition-colors"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-muted-foreground flex items-center gap-2">
                  <Upload className="w-4 h-4" />
                  {certFile ? certFile.name : 'Click to upload certificate'}
                </span>
                {certFile && (
                  <X
                    className="w-4 h-4 cursor-pointer hover:text-destructive"
                    onClick={(e) => {
                      e.stopPropagation();
                      setCertFile(null);
                    }}
                  />
                )}
              </div>
              <input
                ref={certInputRef}
                type="file"
                hidden
                onChange={handleFileChange(setCertFile)}
                accept=".crt,.pem,.cert"
              />
            </div>
          </div>

          {/* Private key file upload */}
          <div className="space-y-2">
            <Label>Private Key (Optional)</Label>
            <div
              onClick={() => keyInputRef.current?.click()}
              className="border-2 border-dashed rounded-lg p-4 cursor-pointer hover:bg-muted transition-colors"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-muted-foreground flex items-center gap-2">
                  <Upload className="w-4 h-4" />
                  {keyFile ? keyFile.name : 'Click to upload private key'}
                </span>
                {keyFile && (
                  <X
                    className="w-4 h-4 cursor-pointer hover:text-destructive"
                    onClick={(e) => {
                      e.stopPropagation();
                      setKeyFile(null);
                    }}
                  />
                )}
              </div>
              <input
                ref={keyInputRef}
                type="file"
                hidden
                onChange={handleFileChange(setKeyFile)}
                accept=".key,.pem"
              />
            </div>
          </div>

          {/* Auto-connect checkbox */}
          <div className="flex items-center space-x-2">
            <Checkbox
              id="auto"
              checked={autoConnect}
              onCheckedChange={(checked) => setAutoConnect(checked as boolean)}
            />
            <Label htmlFor="auto" className="cursor-pointer">
              Auto-connect on startup
            </Label>
          </div>

          <Button type="submit" disabled={loading || isLoading || !configFile} className="w-full">
            {loading || isLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
            Create VPN Profile
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
