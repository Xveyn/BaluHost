# WireGuard VPN Integration - Fritz!Box Config Upload

## 📋 Übersicht

Dieses Dokument beschreibt die Integration von WireGuard VPN mit Fritz!Box Config-Upload für das BaluHost NAS-System.

### Ziel
Admins können eine von der Fritz!Box exportierte WireGuard-Konfiguration hochladen, die dann über QR-Codes an mobile Clients verteilt wird. Clients können sich damit per VPN mit dem Heimnetz verbinden, wenn sie unterwegs sind.

### Architektur-Flow
```
Fritz!Box (Export .conf)
    ↓
Webapp (Admin Upload)
    ↓
Backend (Speicherung + Verschlüsselung)
    ↓
QR-Code Generierung (Mobile Device Registration)
    ↓
Android App (Import + WireGuard Tunnel)
```

---

## ✅ Aktueller Stand (Bereits Implementiert)

### Backend (FastAPI)
- ✅ **VPN Service** (`app/services/vpn.py`)
  - Auto-Generierung von WireGuard Client-Configs
  - Key-Management (Private/Public Keys, Preshared Keys)
  - Client IP-Verwaltung (10.8.0.0/24 Netzwerk)
  - Datenbank-Modelle: `VPNClient`, `VPNConfig`

- ✅ **API Routes** (`app/api/routes/vpn.py`)
  - `POST /api/vpn/generate-config` - Client-Config erstellen
  - `GET /api/vpn/clients` - Clients des Users auflisten
  - `GET /api/vpn/clients/{id}` - Client-Details
  - `PATCH /api/vpn/clients/{id}` - Client bearbeiten
  - `DELETE /api/vpn/clients/{id}` - Client löschen

- ✅ **Mobile Integration** (`app/services/mobile.py`)
  - QR-Code-Generierung mit eingebettetem VPN-Config (Base64)
  - Optional: VPN-Config beim Device-Pairing mitgeben
  - Checkbox "include_vpn" beim Token-Generieren

### Frontend (React Webapp)
- ✅ **MobileDevicesPage** (`client/src/pages/MobileDevicesPage.tsx`)
  - Checkbox "VPN-Konfiguration einschließen"
  - QR-Code-Anzeige mit VPN-Config
  - Token-Generierung mit VPN-Option

- ✅ **API Client** (`client/src/lib/api.ts`)
  - `generateMobileToken(includeVpn, deviceName, validityDays)`
  - TypeScript-Interfaces: `MobileRegistrationToken`

### Android App
- ✅ **VPN Screen** (`presentation/ui/screens/vpn/VpnScreen.kt`)
  - UI für VPN-Verbindung (Connect/Disconnect)
  - Status-Anzeige (Connected/Disconnected)
  - Connection Details (Server, Encryption)
  - VPN Permission Handling

- ✅ **Import UseCase** (`domain/usecase/vpn/ImportVpnConfigUseCase.kt`)
  - QR-Code-Import (Base64-dekodiert)
  - WireGuard Config-Parser
  - Speicherung in PreferencesManager

- ✅ **VPN ViewModel** (`presentation/ui/screens/vpn/VpnViewModel.kt`)
  - State Management
  - Connect/Disconnect Logic
  - Error Handling

---

## ❌ Was FEHLT - Neue Anforderung

### Problem
Das aktuelle System **generiert automatisch** neue WireGuard-Configs für jeden Client mit eigenem Keypair und IP-Adresse. 

### Gewünschte Lösung
Admin soll eine **Fritz!Box WireGuard-Config hochladen** können, die dann an **alle Clients** verteilt wird (shared config model statt per-client model).

### Fritz!Box Config-Format (Beispiel)
```ini
[Interface]
PrivateKey = KItzHLsCg9FvCa6fXYcB7utTCrRn6pjHbRdtkH4z230=
Address = 192.168.178.201/24,fddc:c98b:ce8e::201/64
DNS = 192.168.178.1,fddc:c98b:ce8e::ab6:57ff:fe34:f1bf
DNS = fritz.box

[Peer]
PublicKey = oLAu4Qna34EdumQqGzVtPJeIN8UbppSbUb5MUcRTnl8=
PresharedKey = aY6Ed1NBWd5xSUo80hAk/ZCboHqIW80pJ8NWX179wYU=
AllowedIPs = 192.168.178.0/24,0.0.0.0/0,fddc:c98b:ce8e::/64,::/0
Endpoint = 91474tdd5hs9me4e.myfritz.net:58411
PersistentKeepalive = 25
```

---

## 🎯 Benötigte Implementierung

### 1. Backend - Fritz!Box Config Management

#### 1.1 Database Model
**Neue Tabelle:** `fritzbox_vpn_configs`

```python
# app/models/vpn.py
class FritzBoxVPNConfig(Base):
    __tablename__ = "fritzbox_vpn_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Encrypted sensitive data
    private_key_encrypted = Column(String, nullable=False)
    preshared_key_encrypted = Column(String, nullable=False)
    
    # Public config data
    address = Column(String, nullable=False)  # z.B. "192.168.178.201/24"
    dns_servers = Column(String, nullable=False)  # Komma-separiert
    peer_public_key = Column(String, nullable=False)
    allowed_ips = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)  # DynDNS:Port
    persistent_keepalive = Column(Integer, default=25)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    uploaded_by = relationship("User", back_populates="vpn_configs")
```

#### 1.2 Pydantic Schemas
**Erweiterung:** `app/schemas/vpn.py`

```python
class FritzBoxConfigUpload(BaseModel):
    """Schema for uploading Fritz!Box WireGuard config."""
    config_content: str = Field(..., description="Raw .conf file content")

class FritzBoxConfigResponse(BaseModel):
    """Schema for Fritz!Box config response."""
    id: int
    address: str
    dns_servers: str
    endpoint: str
    allowed_ips: str
    persistent_keepalive: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    config_base64: str = Field(..., description="Base64 encoded config for QR codes")
    
    class Config:
        from_attributes = True

class FritzBoxConfigSummary(BaseModel):
    """Summary info (ohne sensitive Daten)."""
    id: int
    endpoint: str
    dns_servers: str
    is_active: bool
    created_at: datetime
```

#### 1.3 Service-Methoden
**Erweiterung:** `app/services/vpn.py`

```python
class VPNService:
    # ... existing methods ...
    
    @staticmethod
    def parse_fritzbox_config(config_content: str) -> dict:
        """
        Parse Fritz!Box WireGuard config file.
        
        Returns:
            dict with keys: private_key, address, dns, peer_public_key,
                           preshared_key, allowed_ips, endpoint, keepalive
        """
        config = {}
        current_section = None
        
        for line in config_content.split('\n'):
            line = line.strip()
            
            if line.startswith('['):
                current_section = line
            elif current_section == '[Interface]':
                if line.startswith('PrivateKey'):
                    config['private_key'] = line.split('=')[1].strip()
                elif line.startswith('Address'):
                    config['address'] = line.split('=')[1].strip()
                elif line.startswith('DNS'):
                    dns = config.get('dns_servers', '')
                    new_dns = line.split('=')[1].strip()
                    config['dns_servers'] = f"{dns},{new_dns}" if dns else new_dns
            elif current_section == '[Peer]':
                if line.startswith('PublicKey'):
                    config['peer_public_key'] = line.split('=')[1].strip()
                elif line.startswith('PresharedKey'):
                    config['preshared_key'] = line.split('=')[1].strip()
                elif line.startswith('AllowedIPs'):
                    config['allowed_ips'] = line.split('=')[1].strip()
                elif line.startswith('Endpoint'):
                    config['endpoint'] = line.split('=')[1].strip()
                elif line.startswith('PersistentKeepalive'):
                    config['persistent_keepalive'] = int(line.split('=')[1].strip())
        
        return config
    
    @staticmethod
    def upload_fritzbox_config(
        db: Session,
        config_content: str,
        user_id: int
    ) -> FritzBoxConfigResponse:
        """
        Parse and save Fritz!Box WireGuard config.
        
        - Parses config file
        - Encrypts sensitive keys (PrivateKey, PresharedKey)
        - Saves to database
        - Deactivates old configs
        """
        # Parse config
        parsed = VPNService.parse_fritzbox_config(config_content)
        
        # Encrypt sensitive keys
        from app.services.vpn_encryption import VPNEncryption
        private_key_encrypted = VPNEncryption.encrypt_key(parsed['private_key'])
        preshared_key_encrypted = VPNEncryption.encrypt_key(parsed['preshared_key'])
        
        # Deactivate old configs
        db.query(FritzBoxVPNConfig).update({"is_active": False})
        
        # Create new config
        config = FritzBoxVPNConfig(
            private_key_encrypted=private_key_encrypted,
            preshared_key_encrypted=preshared_key_encrypted,
            address=parsed['address'],
            dns_servers=parsed['dns_servers'],
            peer_public_key=parsed['peer_public_key'],
            allowed_ips=parsed['allowed_ips'],
            endpoint=parsed['endpoint'],
            persistent_keepalive=parsed.get('persistent_keepalive', 25),
            is_active=True,
            uploaded_by_user_id=user_id
        )
        
        db.add(config)
        db.commit()
        db.refresh(config)
        
        # Generate config_base64 for response
        config_base64 = VPNService.get_fritzbox_config_base64(db, config.id)
        
        return FritzBoxConfigResponse(
            id=config.id,
            address=config.address,
            dns_servers=config.dns_servers,
            endpoint=config.endpoint,
            allowed_ips=config.allowed_ips,
            persistent_keepalive=config.persistent_keepalive,
            is_active=config.is_active,
            created_at=config.created_at,
            updated_at=config.updated_at,
            config_base64=config_base64
        )
    
    @staticmethod
    def get_fritzbox_config_base64(db: Session, config_id: int = None) -> str:
        """
        Get Fritz!Box config as Base64 (for QR codes).
        
        If config_id is None, returns active config.
        """
        if config_id:
            config = db.query(FritzBoxVPNConfig).filter(
                FritzBoxVPNConfig.id == config_id
            ).first()
        else:
            config = db.query(FritzBoxVPNConfig).filter(
                FritzBoxVPNConfig.is_active == True
            ).first()
        
        if not config:
            raise ValueError("No Fritz!Box VPN config found")
        
        # Decrypt keys
        from app.services.vpn_encryption import VPNEncryption
        private_key = VPNEncryption.decrypt_key(config.private_key_encrypted)
        preshared_key = VPNEncryption.decrypt_key(config.preshared_key_encrypted)
        
        # Rebuild config file
        dns_lines = '\n'.join([f"DNS = {dns}" for dns in config.dns_servers.split(',')])
        
        config_content = f"""[Interface]
PrivateKey = {private_key}
Address = {config.address}
{dns_lines}

[Peer]
PublicKey = {config.peer_public_key}
PresharedKey = {preshared_key}
AllowedIPs = {config.allowed_ips}
Endpoint = {config.endpoint}
PersistentKeepalive = {config.persistent_keepalive}
"""
        
        # Base64 encode
        import base64
        return base64.b64encode(config_content.encode()).decode()
    
    @staticmethod
    def get_active_fritzbox_config(db: Session) -> FritzBoxVPNConfig | None:
        """Get currently active Fritz!Box config."""
        return db.query(FritzBoxVPNConfig).filter(
            FritzBoxVPNConfig.is_active == True
        ).first()
    
    @staticmethod
    def delete_fritzbox_config(db: Session, config_id: int, user_id: int) -> bool:
        """Delete Fritz!Box config (admin only)."""
        config = db.query(FritzBoxVPNConfig).filter(
            FritzBoxVPNConfig.id == config_id
        ).first()
        
        if not config:
            return False
        
        db.delete(config)
        db.commit()
        return True
```

#### 1.4 Encryption Service
**Neue Datei:** `app/services/vpn_encryption.py`

```python
"""VPN key encryption/decryption using Fernet (AES-128)."""

from cryptography.fernet import Fernet
from app.core.config import settings

class VPNEncryption:
    """Handle encryption/decryption of VPN keys."""
    
    @staticmethod
    def encrypt_key(key: str) -> str:
        """
        Encrypt a WireGuard key using Fernet.
        
        Args:
            key: Plain text key (Base64 string)
            
        Returns:
            Encrypted key (Base64)
        """
        if not settings.vpn_encryption_key:
            raise ValueError("VPN_ENCRYPTION_KEY not configured")
        
        cipher = Fernet(settings.vpn_encryption_key.encode())
        encrypted = cipher.encrypt(key.encode())
        return encrypted.decode()
    
    @staticmethod
    def decrypt_key(encrypted_key: str) -> str:
        """
        Decrypt a WireGuard key using Fernet.
        
        Args:
            encrypted_key: Encrypted key (Base64)
            
        Returns:
            Plain text key (Base64 string)
        """
        if not settings.vpn_encryption_key:
            raise ValueError("VPN_ENCRYPTION_KEY not configured")
        
        cipher = Fernet(settings.vpn_encryption_key.encode())
        decrypted = cipher.decrypt(encrypted_key.encode())
        return decrypted.decode()
```

**Config-Erweiterung:** `app/core/config.py`
```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # VPN encryption key (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    vpn_encryption_key: str = ""
```

**Environment Variable:** `.env`
```bash
VPN_ENCRYPTION_KEY=<generiert via Fernet.generate_key()>
```

#### 1.5 API Routes
**Erweiterung:** `app/api/routes/vpn.py`

```python
from app.api import deps

@router.post("/fritzbox/upload", response_model=FritzBoxConfigResponse)
async def upload_fritzbox_config(
    config_data: FritzBoxConfigUpload,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(deps.get_current_admin_user)  # Admin only!
):
    """
    Upload Fritz!Box WireGuard configuration (Admin only).
    
    - Parses .conf file content
    - Encrypts sensitive keys
    - Deactivates old configs
    - Returns config with Base64 for QR codes
    """
    try:
        config = VPNService.upload_fritzbox_config(
            db=db,
            config_content=config_data.config_content,
            user_id=current_user.id
        )
        return config
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid config format: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload config: {str(e)}"
        )

@router.get("/fritzbox/config", response_model=FritzBoxConfigSummary)
async def get_fritzbox_config(
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Get active Fritz!Box VPN config summary (ohne sensitive Daten).
    """
    config = VPNService.get_active_fritzbox_config(db)
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Fritz!Box VPN config found"
        )
    
    return FritzBoxConfigSummary(
        id=config.id,
        endpoint=config.endpoint,
        dns_servers=config.dns_servers,
        is_active=config.is_active,
        created_at=config.created_at
    )

@router.delete("/fritzbox/config/{config_id}")
async def delete_fritzbox_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(deps.get_current_admin_user)  # Admin only!
):
    """
    Delete Fritz!Box VPN config (Admin only).
    """
    success = VPNService.delete_fritzbox_config(db, config_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Config not found"
        )
    
    return {"message": "Config deleted successfully"}

@router.get("/fritzbox/qr")
async def get_fritzbox_qr_code(
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Get Fritz!Box config as Base64 for QR code generation.
    """
    try:
        config_base64 = VPNService.get_fritzbox_config_base64(db)
        return {"config_base64": config_base64}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
```

#### 1.6 Mobile Service Integration
**Änderung:** `app/services/mobile.py`

```python
# In generate_registration_token():
if include_vpn:
    try:
        # PRIORITÄT 1: Fritz!Box Config (wenn vorhanden)
        fritzbox_config = db.query(FritzBoxVPNConfig).filter(
            FritzBoxVPNConfig.is_active == True
        ).first()
        
        if fritzbox_config:
            # Nutze Fritz!Box Config
            vpn_config_base64 = VPNService.get_fritzbox_config_base64(db)
        else:
            # FALLBACK: Auto-generiere Client-Config (wie bisher)
            from app.services.vpn import VPNService
            server_endpoint = server_url.replace("http://", "").replace("https://", "").split(":")[0]
            vpn_response = VPNService.create_client_config(
                db=db,
                user_id=int(user_id),
                device_name=device_name,
                server_public_endpoint=server_endpoint,
            )
            vpn_config_base64 = vpn_response.config_base64
    except Exception as e:
        print(f"Warning: VPN config generation failed: {e}")
```

---

### 2. Frontend - VPN Management UI

#### 2.1 Neue Komponente: VpnManagement.tsx
**Neue Datei:** `client/src/components/VpnManagement.tsx`

```tsx
import { useState, useEffect } from 'react';
import { Upload, Wifi, Trash2, QrCode, Check, AlertCircle } from 'lucide-react';
import QRCode from 'qrcode.react';
import { apiClient } from '../lib/api';

interface FritzBoxConfig {
  id: number;
  endpoint: string;
  dns_servers: string;
  is_active: boolean;
  created_at: string;
}

export default function VpnManagement() {
  const [config, setConfig] = useState<FritzBoxConfig | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [qrData, setQrData] = useState<string | null>(null);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await apiClient.get('/api/vpn/fritzbox/config');
      setConfig(response.data);
      
      // Load QR code data
      const qrResponse = await apiClient.get('/api/vpn/fritzbox/qr');
      setQrData(qrResponse.data.config_base64);
    } catch (err: any) {
      if (err.response?.status !== 404) {
        setError('Config konnte nicht geladen werden');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadFile(file);
      setError(null);
      setSuccess(null);
    }
  };

  const handleUpload = async () => {
    if (!uploadFile) return;

    try {
      setUploading(true);
      setError(null);
      setSuccess(null);

      // Read file content
      const fileContent = await uploadFile.text();

      // Upload to backend
      await apiClient.post('/api/vpn/fritzbox/upload', {
        config_content: fileContent
      });

      setSuccess('Fritz!Box VPN-Konfiguration erfolgreich hochgeladen!');
      setUploadFile(null);
      
      // Reload config
      await loadConfig();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload fehlgeschlagen');
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async () => {
    if (!config || !confirm('VPN-Konfiguration wirklich löschen?')) return;

    try {
      await apiClient.delete(`/api/vpn/fritzbox/config/${config.id}`);
      setSuccess('Konfiguration gelöscht');
      setConfig(null);
      setQrData(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Löschen fehlgeschlagen');
    }
  };

  if (loading) {
    return (
      <div className="text-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500 mx-auto"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Upload Section */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
          <Upload className="w-5 h-5 mr-2 text-sky-400" />
          Fritz!Box WireGuard Config hochladen
        </h3>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-start gap-2 text-red-400">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <span className="text-sm">{error}</span>
          </div>
        )}

        {success && (
          <div className="mb-4 p-3 bg-green-500/10 border border-green-500/30 rounded-lg flex items-start gap-2 text-green-400">
            <Check className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <span className="text-sm">{success}</span>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              WireGuard Konfigurationsdatei (.conf)
            </label>
            <input
              type="file"
              accept=".conf"
              onChange={handleFileSelect}
              className="block w-full text-sm rounded-lg border border-slate-700 bg-slate-800 text-slate-100 px-3 py-2"
            />
            {uploadFile && (
              <p className="mt-2 text-sm text-slate-400">
                Ausgewählt: {uploadFile.name}
              </p>
            )}
          </div>

          <button
            onClick={handleUpload}
            disabled={!uploadFile || uploading}
            className="w-full sm:w-auto px-6 py-2.5 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploading ? 'Wird hochgeladen...' : 'Hochladen'}
          </button>
        </div>

        <div className="mt-4 p-3 bg-slate-800/50 border border-slate-700/50 rounded-lg">
          <p className="text-xs text-slate-400">
            💡 <strong>Hinweis:</strong> Die Fritz!Box-Konfiguration wird verschlüsselt gespeichert und über QR-Codes an mobile Geräte verteilt.
          </p>
        </div>
      </div>

      {/* Current Config Display */}
      {config && (
        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold flex items-center text-white">
              <Wifi className="w-5 h-5 mr-2 text-green-400" />
              Aktive VPN-Konfiguration
            </h3>
            <button
              onClick={handleDelete}
              className="p-2 text-red-400 hover:text-red-300 transition-colors"
              title="Konfiguration löschen"
            >
              <Trash2 className="w-5 h-5" />
            </button>
          </div>

          <div className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-slate-400">Server-Endpoint:</span>
                <p className="text-white font-medium">{config.endpoint}</p>
              </div>
              <div>
                <span className="text-slate-400">DNS-Server:</span>
                <p className="text-white font-medium">{config.dns_servers}</p>
              </div>
              <div>
                <span className="text-slate-400">Status:</span>
                <p className="text-green-400 font-medium flex items-center gap-1">
                  <Check className="w-4 h-4" /> Aktiv
                </p>
              </div>
              <div>
                <span className="text-slate-400">Hochgeladen am:</span>
                <p className="text-white font-medium">
                  {new Date(config.created_at).toLocaleString('de-DE')}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* QR Code Preview */}
      {qrData && (
        <div className="card border-slate-800/60 bg-slate-900/55">
          <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
            <QrCode className="w-5 h-5 mr-2 text-sky-400" />
            QR-Code Vorschau (für Clients)
          </h3>

          <div className="bg-white p-4 rounded-lg inline-block">
            <QRCode value={qrData} size={256} level="H" />
          </div>

          <p className="mt-4 text-sm text-slate-400">
            Dieser QR-Code wird automatisch beim Generieren eines Mobile-Device-Tokens eingebettet, wenn "VPN einschließen" aktiviert ist.
          </p>
        </div>
      )}
    </div>
  );
}
```

#### 2.2 Integration in SettingsPage
**Änderung:** `client/src/pages/SettingsPage.tsx`

```tsx
// Import hinzufügen
import VpnManagement from '../components/VpnManagement';

// In Tabs-Array (nur für Admin):
{[
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'security', label: 'Security', icon: Lock },
  { id: 'storage', label: 'Storage', icon: HardDrive },
  { id: 'activity', label: 'Activity', icon: Activity },
  ...(profile?.role === 'admin' ? [
    { id: 'backup', label: 'Backup', icon: Database },
    { id: 'vpn', label: 'VPN', icon: Wifi }  // NEU
  ] : [])
].map(tab => (
  // ... existing tab rendering
))}

// Tab Content Rendering:
{activeTab === 'vpn' && profile?.role === 'admin' && (
  <VpnManagement />
)}
```

#### 2.3 Dependencies
**Package Installation:**
```bash
cd client
npm install qrcode.react
npm install --save-dev @types/qrcode.react
```

---

### 3. Android App - Keine Änderungen nötig!

#### 3.1 Warum?
Die Android-App ist **generisch** und behandelt alle WireGuard-Configs gleich:

1. **QR-Code Import** (`ImportVpnConfigUseCase`)
   - Dekodiert Base64
   - Parsed [Interface] und [Peer]
   - Speichert in PreferencesManager

2. **VPN Connection** (`VpnScreen`, `VpnViewModel`)
   - Verwendet gespeicherte Config
   - Startet WireGuard Tunnel
   - Zeigt Status an

**Es ist egal, ob die Config:**
- Von Fritz!Box kommt (uploaded by admin)
- Oder auto-generiert wurde (per-client)

Beide haben das gleiche WireGuard-Format!

#### 3.2 Bestehende Funktionen (bleiben unverändert)
- ✅ QR-Scanner beim Device Registration
- ✅ VPN-Config-Import und Speicherung
- ✅ VPN-Screen UI (Connect/Disconnect)
- ✅ Heimnetz-Erkennung (Auto-Connect wenn außerhalb)
- ✅ WireGuard Tunnel Management

---

## 🔐 Sicherheitsaspekte

### Key Encryption
- **PrivateKey** und **PresharedKey** werden mit **Fernet (AES-128)** verschlüsselt
- Master-Key in `.env` (`VPN_ENCRYPTION_KEY`)
- Keys niemals im Klartext in DB oder Logs

### Access Control
- **Upload:** Nur Admins (`get_current_admin_user`)
- **Download:** Authentifizierte User (für QR-Code)
- **Delete:** Nur Admins

### Best Practices
- Config-File-Validierung vor Upload
- Nur **eine aktive** Fritz!Box-Config
- Alte Configs werden deaktiviert (nicht gelöscht → Audit-Trail)
- Rate-Limiting auf Upload-Endpoint

---

## 📊 Datenbank-Migration

### Alembic Migration erstellen
```bash
cd backend
alembic revision -m "Add FritzBox VPN config table"
```

### Migration-File Inhalt:
```python
def upgrade():
    op.create_table(
        'fritzbox_vpn_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('private_key_encrypted', sa.String(), nullable=False),
        sa.Column('preshared_key_encrypted', sa.String(), nullable=False),
        sa.Column('address', sa.String(), nullable=False),
        sa.Column('dns_servers', sa.String(), nullable=False),
        sa.Column('peer_public_key', sa.String(), nullable=False),
        sa.Column('allowed_ips', sa.String(), nullable=False),
        sa.Column('endpoint', sa.String(), nullable=False),
        sa.Column('persistent_keepalive', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fritzbox_vpn_configs_id', 'fritzbox_vpn_configs', ['id'])
    op.create_index('ix_fritzbox_vpn_configs_is_active', 'fritzbox_vpn_configs', ['is_active'])

def downgrade():
    op.drop_index('ix_fritzbox_vpn_configs_is_active', 'fritzbox_vpn_configs')
    op.drop_index('ix_fritzbox_vpn_configs_id', 'fritzbox_vpn_configs')
    op.drop_table('fritzbox_vpn_configs')
```

---

## 🧪 Testing-Plan

### 1. Backend Unit Tests
```python
# tests/test_vpn_service.py
def test_parse_fritzbox_config():
    config_content = """
[Interface]
PrivateKey = KItzHLsCg9FvCa6fXYcB7utTCrRn6pjHbRdtkH4z230=
Address = 192.168.178.201/24
DNS = 192.168.178.1

[Peer]
PublicKey = oLAu4Qna34EdumQqGzVtPJeIN8UbppSbUb5MUcRTnl8=
PresharedKey = aY6Ed1NBWd5xSUo80hAk/ZCboHqIW80pJ8NWX179wYU=
AllowedIPs = 192.168.178.0/24,0.0.0.0/0
Endpoint = example.myfritz.net:58411
PersistentKeepalive = 25
"""
    parsed = VPNService.parse_fritzbox_config(config_content)
    assert parsed['endpoint'] == 'example.myfritz.net:58411'
    assert parsed['persistent_keepalive'] == 25

def test_encryption_decryption():
    key = "test_key_1234567890abcdef"
    encrypted = VPNEncryption.encrypt_key(key)
    decrypted = VPNEncryption.decrypt_key(encrypted)
    assert key == decrypted
```

### 2. Integration Tests
1. **Upload Fritz!Box Config:**
   - POST `/api/vpn/fritzbox/upload` mit .conf Content
   - Verify: Config in DB, keys verschlüsselt

2. **QR-Code Generierung:**
   - GET `/api/vpn/fritzbox/qr`
   - Verify: Base64 string, decodiert zu valider Config

3. **Mobile Token mit VPN:**
   - POST `/api/mobile/register-token` mit `include_vpn=true`
   - Verify: QR-Code enthält Fritz!Box Config (nicht auto-generated)

### 3. Frontend E2E Tests
1. Admin-Login → Settings → VPN Tab
2. Upload .conf File
3. Verify: Config angezeigt, QR-Code sichtbar
4. MobileDevices Page → "VPN einschließen" aktiviert
5. Verify: QR-Code enthält Fritz!Box Config

### 4. Android Integration Test
1. Scan QR-Code vom Webapp
2. Verify: VPN-Config importiert
3. Verify: VPN Screen zeigt Endpoint korrekt
4. Connect VPN
5. Verify: Tunnel aktiv, Heimnetz erreichbar

---

## 📝 API-Dokumentation

### Endpoints

#### `POST /api/vpn/fritzbox/upload`
**Auth:** Admin only  
**Request:**
```json
{
  "config_content": "[Interface]\nPrivateKey = ...\n..."
}
```
**Response:**
```json
{
  "id": 1,
  "address": "192.168.178.201/24",
  "dns_servers": "192.168.178.1,fddc:c98b:ce8e::ab6:57ff:fe34:f1bf",
  "endpoint": "91474tdd5hs9me4e.myfritz.net:58411",
  "allowed_ips": "192.168.178.0/24,0.0.0.0/0,fddc:c98b:ce8e::/64,::/0",
  "persistent_keepalive": 25,
  "is_active": true,
  "created_at": "2025-12-14T15:30:00",
  "updated_at": "2025-12-14T15:30:00",
  "config_base64": "W0ludGVyZmFjZV0K..."
}
```

#### `GET /api/vpn/fritzbox/config`
**Auth:** User  
**Response:**
```json
{
  "id": 1,
  "endpoint": "91474tdd5hs9me4e.myfritz.net:58411",
  "dns_servers": "192.168.178.1,fddc:c98b:ce8e::ab6:57ff:fe34:f1bf",
  "is_active": true,
  "created_at": "2025-12-14T15:30:00"
}
```

#### `GET /api/vpn/fritzbox/qr`
**Auth:** User  
**Response:**
```json
{
  "config_base64": "W0ludGVyZmFjZV0KUHJpdmF0ZUtleS..."
}
```

#### `DELETE /api/vpn/fritzbox/config/{id}`
**Auth:** Admin only  
**Response:**
```json
{
  "message": "Config deleted successfully"
}
```

---

## 🚀 Implementierungs-Schritte

### Phase 1: Backend Foundation (45 Min)
1. ✅ Environment Variable `VPN_ENCRYPTION_KEY` generieren
2. ✅ Config-Erweiterung in `settings.py`
3. ✅ Encryption Service `vpn_encryption.py`
4. ✅ Database Model `FritzBoxVPNConfig`
5. ✅ Alembic Migration erstellen & ausführen
6. ✅ Pydantic Schemas in `vpn.py`

### Phase 2: Backend Service & API (60 Min)
1. ✅ Service-Methoden in `vpn.py`:
   - `parse_fritzbox_config()`
   - `upload_fritzbox_config()`
   - `get_fritzbox_config_base64()`
   - `get_active_fritzbox_config()`
   - `delete_fritzbox_config()`
2. ✅ API Routes in `routes/vpn.py`
3. ✅ Mobile Service Integration (`mobile.py`)
4. ✅ Unit Tests

### Phase 3: Frontend UI (60 Min)
1. ✅ Install `qrcode.react` dependency
2. ✅ `VpnManagement.tsx` Component erstellen
3. ✅ `SettingsPage.tsx` Integration (VPN Tab)
4. ✅ API Client Functions
5. ✅ Styling & UX

### Phase 4: Testing & Validation (30 Min)
1. ✅ Backend Unit Tests
2. ✅ Upload echte Fritz!Box Config
3. ✅ QR-Code Generierung testen
4. ✅ Android: QR-Code scannen & importieren
5. ✅ VPN-Verbindung testen

**Gesamt: ~3 Stunden**

---

## 📚 Weiterführende Dokumentation

- [WireGuard Protocol](https://www.wireguard.com/)
- [Fritz!Box WireGuard Setup](https://avm.de/service/wissensdatenbank/)
- [Cryptography Fernet](https://cryptography.io/en/latest/fernet/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)

---

## ✅ Checkliste vor Start

- [ ] Backend `.env` hat `VPN_ENCRYPTION_KEY`
- [ ] User hat Admin-Rechte in Webapp
- [ ] Fritz!Box WireGuard Config exportiert (`.conf` File)
- [ ] Android App auf physischem Gerät (für VPN-Test)
- [ ] Netzwerk-Setup: DynDNS/Port-Forwarding aktiv

---

**Letzte Aktualisierung:** 14. Dezember 2025  
**Version:** 1.0  
**Status:** Bereit für Implementierung
