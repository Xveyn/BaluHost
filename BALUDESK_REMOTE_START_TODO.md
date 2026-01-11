# Feature: Remote BaluHost Server Start via SSH/VPN

**Status:** Planning  
**Priority:** High  
**Complexity:** Medium (SSH handling, VPN detection, profiles)

---

## Übersicht

Benutzer können mehrere BaluHost Server als "Profile" auf der BaluDesk Login-Seite hinzufügen. Von dort aus können sie diese remote starten:
- **Gleches Netzwerk:** Direkter SSH-Zugriff
- **Externes Netzwerk:** Automatische VPN-Verbindung → SSH-Zugriff

---

## Backend Anforderungen

### 1. Database Schema

#### Tabelle: `server_profiles`
- [ ] **Neue Tabelle: `server_profiles`**
  - `id` (PK)
  - `user_id` (FK → users)
  - `name` (String) - z.B. "Home NAS", "Office Server"
  - `ssh_host` (String) - IP/Hostname
  - `ssh_port` (Integer, default 22)
  - `ssh_username` (String) - SSH User
  - `ssh_key_encrypted` (Text) - Private Key (verschlüsselt)
  - `is_local_network` (Boolean) - Gleches Netzwerk?
  - `vpn_profile_id` (FK → vpn_profiles, nullable) - VPN-Profil falls erforderlich
  - `power_on_command` (String) - SSH Befehl zum Starten (z.B. "systemctl start baluhost-backend")
  - `created_at` (DateTime)
  - `last_used` (DateTime, nullable)
  - Indexes: `(user_id, name)`, `(user_id, created_at)`, `(vpn_profile_id)`

#### Tabelle: `vpn_profiles`
- [ ] **Neue Tabelle: `vpn_profiles`** (analog zu BaluHost VPN Profiles)
  - `id` (PK)
  - `user_id` (FK → users)
  - `name` (String) - z.B. "Home VPN", "Office OpenVPN"
  - `vpn_type` (Enum) - "openvpn", "wireguard", "custom"
  - `config_file_encrypted` (Text) - .ovpn/.conf Datei (verschlüsselt)
  - `certificate_encrypted` (Text, nullable) - Optional: Client-Zertifikat (verschlüsselt)
  - `private_key_encrypted` (Text, nullable) - Optional: Private Key (verschlüsselt)
  - `auto_connect` (Boolean, default false)
  - `description` (Text, nullable)
  - `created_at` (DateTime)
  - `updated_at` (DateTime)
  - Indexes: `(user_id, name)`, `(user_id, created_at)`

#### Beziehungen
- `server_profiles.vpn_profile_id` → `vpn_profiles.id` (Optional, viele Server können ein VPN-Profil nutzen)

### 2. API Endpoints

**POST /api/server-profiles**
```json
Request:
{
  "name": "Home NAS",
  "ssh_host": "192.168.1.100",
  "ssh_port": 22,
  "ssh_username": "admin",
  "ssh_private_key": "-----BEGIN PRIVATE KEY-----...",
  "is_local_network": true,
  "vpn_profile_id": null,  # Optional, wenn VPN erforderlich
  "power_on_command": "systemctl start baluhost-backend"
}

Response:
{
  "id": "uuid",
  "name": "Home NAS",
  "ssh_host": "192.168.1.100",
  "status": "created"
}
```

**GET /api/server-profiles** (List all profiles for user)
```json
Response:
[
  {
    "id": "uuid",
    "name": "Home NAS",
    "ssh_host": "192.168.1.100",
    "is_local_network": true,
    "vpn_profile_id": null,
    "last_used": "2026-01-06T10:30:00Z"
  }
]
```

**VPN Profile Endpoints** (analog zu BaluHost)

**POST /api/vpn-profiles**
```json
Request:
{
  "name": "Home OpenVPN",
  "vpn_type": "openvpn",
  "config_file": "client.ovpn (als base64 oder upload)",
  "certificate": "ca.crt (optional)",
  "private_key": "client.key (optional)",
  "auto_connect": false,
  "description": "Home network VPN"
}

Response:
{
  "id": "uuid",
  "name": "Home OpenVPN",
  "vpn_type": "openvpn",
  "status": "created"
}
```

**GET /api/vpn-profiles** (List all VPN profiles)
```json
Response:
[
  {
    "id": "uuid",
    "name": "Home OpenVPN",
    "vpn_type": "openvpn",
    "auto_connect": false,
    "created_at": "2026-01-06T09:00:00Z"
  }
]
```

**DELETE /api/vpn-profiles/{id}** (Delete VPN profile)

**POST /api/vpn-profiles/{id}/test-connection** (Test VPN connection)

**PUT /api/server-profiles/{id}** (Edit profile)

**DELETE /api/server-profiles/{id}** (Delete profile)

**POST /api/server-profiles/{id}/start** (Start server)
```json
Response:
{
  "id": "uuid",
  "status": "starting",
  "message": "Server startup command sent"
}
```

**GET /api/server-profiles/{id}/check-connectivity** (Test connection)
```json
Response:
{
  "ssh_reachable": true,
  "local_network": true,
  "needs_vpn": false
}
```

### 3. Backend Services

**SSHService** (`backend/app/services/ssh_service.py`)
- `test_ssh_connection(host, port, username, private_key) → bool`
- `execute_remote_command(host, port, username, private_key, command) → str`
- `start_baluhost_server(profile: ServerProfile) → dict`

**VPNService** (`backend/app/services/vpn_service.py`)
- `is_vpn_connection_active(vpn_profile_id) → bool`
- `connect_vpn(vpn_profile: VPNProfile) → bool` - Verbindung starten
- `disconnect_vpn(vpn_profile_id) → bool` - Verbindung trennen
- `test_vpn_connection(vpn_profile: VPNProfile) → bool` - VPN-Konfiguration testen
- `get_vpn_config(vpn_profile_id) → str` - Konfiguration auslesen
- Unterstützung für OpenVPN und WireGuard

**NetworkService** (`backend/app/services/network_service.py`)
- `detect_network_type(ssh_host, local_subnets) → NetworkType`
- `is_same_network(client_ip, server_ip, subnet_mask) → bool`

**EncryptionService** (Existierend erweitern)
- `encrypt_ssh_key(private_key, user_id) → str`
- `decrypt_ssh_key(encrypted_key, user_id) → str`
- `encrypt_vpn_config(config_content, user_id) → str`
- `decrypt_vpn_config(encrypted_config, user_id) → str`
- SSH Keys und VPN Configs mit User-specific Key verschlüsseln (Envelope Encryption)

**ServerProfileService** (`backend/app/services/server_profile_service.py`)
- `create_profile(user_id, profile_data) → ServerProfile`
- `validate_ssh_credentials(profile) → bool`
- `get_user_profiles(user_id) → List[ServerProfile]`
- `delete_profile(profile_id, user_id) → bool`
- `start_server(profile: ServerProfile) → dict` - Mit VPN-Support

**VPNProfileService** (`backend/app/services/vpn_profile_service.py`) (Neu)
- `create_vpn_profile(user_id, profile_data) → VPNProfile`
- `get_user_vpn_profiles(user_id) → List[VPNProfile]`
- `update_vpn_profile(profile_id, user_id, data) → VPNProfile`
- `delete_vpn_profile(profile_id, user_id) → bool`
- `test_vpn_connection(profile: VPNProfile) → bool`

### 4. Logging & Security
- [ ] Alle SSH-Verbindungen in AuditLog loggen (LOGIN_ATTEMPT, REMOTE_CONNECT)
- [ ] Failed SSH attempts mit IP + Timestamp tracken (Brute-Force-Schutz)
- [ ] Private Keys NICHT im Log speichern
- [ ] Rate-Limiting für Verbindungsversuche
- [ ] SSH-Keys verschlüsselt mit User-Password speichern (Envelope Encryption)

### 5. Dependencies
```python
# requirements.txt hinzufügen:
paramiko==3.4.0          # SSH
cryptography==42.0.0      # SSH Keys + Encryption
pydantic==2.6.0           # Already have it
```

---

## Frontend Anforderungen

### 1. Pages

**Login Page - Erweiterung**
- [ ] "Add Server" Button neben dem Passwort-Input
- [ ] Modal: "Server hinzufügen" mit Formular:
  - Server Name
  - SSH Host/IP
  - SSH Port (default 22)
  - SSH Username
  - SSH Private Key (Upload oder Paste)
  - **VPN Profil** (Dropdown) - Optional
    - "None (Direct)"
    - "Auto-detect"
    - Liste von User-VPN-Profiles
  - Startup Command (optional)
  - "Test Connection" Button
- [ ] Existing Profiles Liste unter Login-Form
  - Zeige: Server Name, Host, VPN (ja/nein), Last Used
  - Actions: Connect, Edit, Delete

**New: Server Profiles Page**
- [ ] CRUD-Interface für Server Profile
  - Create: Form wie oben (mit VPN-Auswahl)
  - Read: Liste mit Details
  - Update: Edit Modal
  - Delete: Confirmation Dialog
- [ ] Test SSH Connection vor dem Speichern
- [ ] Status-Anzeige: "Connected", "Offline", "Auth Failed"

**New: VPN Profiles Page** (analog zu BaluHost)
- [ ] VPN Profile Management
  - Create: Upload .ovpn/.conf Datei
  - Read: Liste mit VPN-Type, Status
  - Update: Re-Upload Datei
  - Delete: Confirmation Dialog
- [ ] Test VPN Connection Button
- [ ] Status-Anzeige: "Connected", "Disconnected", "Error"
- [ ] Auto-Connect Option (nur für häufig genutzte VPNs)

### 2. Components

**ServerProfileForm.tsx**
```typescript
interface ServerProfile {
  id: string;
  name: string;
  ssh_host: string;
  ssh_port: number;
  ssh_username: string;
  is_local_network: boolean;
  vpn_profile_id?: string;  // Optional VPN-Profil
  last_used?: string;
}

interface Props {
  profile?: ServerProfile;
  vpnProfiles?: VPNProfile[];  // Verfügbare VPN-Profile
  onSave: (profile: ServerProfile) => Promise<void>;
  onTestConnection?: (profile: ServerProfile) => Promise<boolean>;
}
```

**ServerProfileList.tsx**
- Zeige alle User-Profile mit VPN-Info
- Filter/Search
- Inline Actions (Start, Edit, Delete)

**VPNProfileForm.tsx** (Neu)
```typescript
interface VPNProfile {
  id: string;
  name: string;
  vpn_type: "openvpn" | "wireguard" | "custom";
  auto_connect: boolean;
  created_at: string;
}

interface Props {
  profile?: VPNProfile;
  onSave: (profile: VPNProfile, configFile: File) => Promise<void>;
  onTest?: (profile: VPNProfile) => Promise<boolean>;
}
```

**VPNProfileList.tsx** (Neu)
- Zeige alle VPN-Profile
- Status-Icons (Connected, Disconnected)
- Inline Actions (Test, Edit, Delete)

**SSHKeyUpload.tsx**
- Datei-Upload oder Text-Paste
- Key-Validierung (RSA, ED25519 Format Check)
- "Copy from clipboard" Button

**VPNFileUpload.tsx** (Neu)
- .ovpn / .conf Datei Upload
- File-Type Validierung
- Größen-Check (max. 1MB)
- Preview (nicht-sensitive Daten zeigen)

**RemoteStartModal.tsx**
- Zeige: "Connecting via VPN..." (wenn VPN erforderlich)
- Dann: "Connecting via SSH..."
- Dann: "Starting Server..."
- Progress-Bar mit Stages
- Fehlerbehandlung mit klaren Fehlermeldungen

### 3. API Client Integration

**Neue Hooks** (`src/hooks/`)
- [ ] `useServerProfiles()` - CRUD Operations
- [ ] `useVPNProfiles()` - VPN Profile CRUD (Neu)
- [ ] `useSSHConnection(profileId)` - Verbindungsstatus
- [ ] `useVPNConnection(vpnProfileId)` - VPN Status (Neu)
- [ ] `useRemoteStart(profileId)` - Server starten mit VPN

**API Service** (`src/api/serverProfiles.ts`)
```typescript
export const serverProfiles = {
  list: () => api.get('/server-profiles'),
  create: (data: CreateProfileDTO) => api.post('/server-profiles', data),
  update: (id: string, data: UpdateProfileDTO) => api.put(`/server-profiles/${id}`, data),
  delete: (id: string) => api.delete(`/server-profiles/${id}`),
  testConnection: (id: string) => api.post(`/server-profiles/${id}/check-connectivity`),
  start: (id: string) => api.post(`/server-profiles/${id}/start`),
}

export const vpnProfiles = {
  list: () => api.get('/vpn-profiles'),
  create: (data: FormData) => api.post('/vpn-profiles', data),  // FormData für File-Upload
  update: (id: string, data: FormData) => api.put(`/vpn-profiles/${id}`, data),
  delete: (id: string) => api.delete(`/vpn-profiles/{id}`),
  testConnection: (id: string) => api.post(`/vpn-profiles/${id}/test-connection`),
}
```

### 4. UI/UX Flows

**Erstes Setup (Neue Installation)**
1. User sieht Login-Seite
2. Klick auf "Add Server"
3. Modal öffnet sich
4. **Optional:** Zuerst VPN-Profil laden (falls erforderlich)
   - Klick auf "Manage VPN Profiles"
   - Upload .ovpn Datei
   - Test Connection
5. Server Form ausfüllen (Name, SSH-Daten, VPN-Profil auswählen)
6. "Test Connection" Klick
   - Falls VPN erforderlich: VPN verbinden → Test SSH → VPN trennen
   - Falls lokal: Direkt SSH Test
7. ✅ Bei Erfolg: Profile speichern
8. ❌ Bei Fehler: Fehler anzeigen, User kann korrigieren

**Login mit bestehendem Server (mit VPN)**
1. User sieht Login-Seite
2. Profile-Liste unter Login-Feld
3. Klick auf gewünschtes Profile (das VPN-Profil zugeordnet hat)
4. Eingabefelder auto-filled (ssh_host, VPN-Info angezeigt)
5. Login Button triggert:
   - VPN verbinden (falls Profile VPN_Profile_ID hat)
   - SSH Connect
   - Baluhost Server Startup Command ausführen
   - Warten auf Server (Polling /health endpoint)
   - Dann Login in normales UI
   - Nach Login: VPN disconnect (oder keep-alive lassen)

### 5. State Management

**Zustände während Remote Start:**
```
IDLE
→ CONNECTING_VPN (falls VPN-Profil gesetzt)
  → VPN_CONNECTED
→ CONNECTING_SSH
  → SSH_CONNECTED
    → EXECUTING_STARTUP_COMMAND
      → STARTUP_SENT
        → WAITING_FOR_SERVER
          → READY / FAILED
```

Error States:
- `VPN_CONNECTION_TIMEOUT` (falls VPN)
- `VPN_AUTH_FAILED` (falls VPN)
- `SSH_TIMEOUT`
- `SSH_AUTH_FAILED`
- `SSH_CONNECTION_REFUSED`
- `STARTUP_COMMAND_FAILED`
- `SERVER_STARTUP_TIMEOUT`

---

## Implementierungs-Reihenfolge

### Phase 1: Grundgerüst (Backend)
1. [ ] Database Migration für `server_profiles` und `vpn_profiles` Tables
2. [ ] Pydantic Schemas für ServerProfile und VPNProfile
3. [ ] SSHService implementieren
4. [ ] VPNService implementieren (OpenVPN + WireGuard Support)
5. [ ] EncryptionService erweitern (SSH-Keys + VPN-Configs)
6. [ ] API Endpoints: Server & VPN CRUD, List, Delete
7. [ ] Tests für SSH-Verbindungen (mit Mock SSH)
8. [ ] Tests für VPN-Konfigurationen (mit Mock VPN)

### Phase 2: Frontend Integration
9. [ ] VPNProfileForm und VPNProfileList Components
10. [ ] ServerProfileForm mit VPN-Auswahl
11. [ ] Login Page erweitern (Profile-Liste + VPN-Anzeige)
12. [ ] API Client Integration (Server + VPN APIs)
13. [ ] Test Connection Flow (SSH + VPN)

### Phase 3: Remote Start Feature
14. [ ] Start Endpoint Backend (mit VPN-Support)
15. [ ] VPN Auto-Connect / Disconnect Logic
16. [ ] RemoteStartModal Component mit VPN-Stages
17. [ ] Polling für Server-Ready-Status
18. [ ] State Management für Multi-Stage Flow

### Phase 4: Polish & Security
19. [ ] Encryption für SSH Keys und VPN Configs
20. [ ] Audit Logging (SSH-Verbindungen, VPN-Events)
21. [ ] Error Handling & User Feedback
22. [ ] Validation & Rate Limiting
23. [ ] VPN Keep-Alive / Disconnect Policy

---

## Testing-Strategie

### Backend Tests
```python
# test_ssh_service.py
test_ssh_connection_successful()
test_ssh_connection_failed()
test_ssh_command_execution()
test_invalid_credentials()
test_connection_timeout()

# test_vpn_service.py (NEU)
test_openvpn_connection_parsing()
test_wireguard_connection_parsing()
test_invalid_vpn_config()
test_vpn_file_encryption()

# test_server_profile_api.py
test_create_profile()
test_list_user_profiles()
test_delete_profile()
test_start_remote_server_with_vpn()
test_start_remote_server_without_vpn()

# test_vpn_profile_api.py (NEU)
test_create_vpn_profile()
test_upload_ovpn_file()
test_list_vpn_profiles()
test_delete_vpn_profile()
test_vpn_encryption()
```

### Frontend Tests
```typescript
// vpnProfileForm.test.tsx (NEU)
test_renders_file_upload()
test_validates_ovpn_format()
test_submits_valid_vpn_profile()
test_handles_api_errors()

// serverProfileForm.test.tsx
test_renders_vpn_profile_dropdown()
test_loads_available_vpn_profiles()
test_validates_required_fields()
test_submits_valid_profile_with_vpn()

// remoteStart.test.tsx
test_shows_vpn_connecting_state()
test_shows_ssh_connecting_state()
test_shows_server_starting_state()
test_polls_for_ready_status()
test_handles_vpn_timeout()
test_handles_ssh_timeout()
test_disconnects_vpn_after_ready()
```

---

## Sicherheitsüberlegungen

⚠️ **Wichtig:**
- [ ] SSH Private Keys NIEMALS im Code/Config speichern → Envelope Encryption
- [ ] VPN Config-Dateien NIEMALS unverschlüsselt speichern → Encryption mit User-Password
- [ ] Beide: Keys mit User-Password verschlüsseln (Envelope Encryption mit Master-Key)
- [ ] SSL/TLS für alle Übertragungen
- [ ] Rate Limiting auf SSH-Verbindungsversuche
- [ ] Rate Limiting auf VPN-Verbindungsversuche
- [ ] Audit Log für alle SSH-Operationen (success/failure)
- [ ] Audit Log für alle VPN-Operationen (connect/disconnect)
- [ ] SSH Key Rotation möglich machen (Profil editierbar)
- [ ] VPN Config Update möglich machen (Re-upload)
- [ ] Warnung: "Diese Verbindungen werden am Server geloggt"
- [ ] Optional: 2FA für Remote-Start
- [ ] VPN Disconnect nach Server-Ready (oder Keep-Alive Option)
- [ ] Sensitive Daten (Keys, Certs) nicht in API-Response zurückgeben

---

## Offene Fragen / Diskussionspunkte

1. **VPN-Integration:** Nur OpenVPN + WireGuard, oder auch andere?
2. **VPN Lifecycle:** Auto-Disconnect nach SSH, oder Connection halten?
3. **VPN Keep-Alive:** Keep VPN active für schnelle Reconnects?
4. **Wake-on-LAN:** Auch als Alternative zu SSH-Start unterstützen?
5. **Persistence:** SSH-Keys / VPN-Certs lokal speichern im Desktop-Client?
6. **Multi-Network:** Mehrere lokale Subnets pro User?
7. **Server Health:** Nach Start automatisch Health-Check Polling?
8. **Fallback:** Was tun, wenn VPN/SSH fehlschlägt? (Retry Logic?)

---

## Schätzungen

| Task | Aufwand | Notes |
|------|---------|-------|
| DB + VPN Endpoints | 4-5h | VPNService ist neuer Komplexität |
| SSH Service | 2h | Paramiko Integration |
| Frontend Basic (Server) | 3-4h | Form + List Components |
| Frontend VPN Management | 2-3h | VPN Upload + List |
| Remote Start Integration | 3-4h | Multi-Stage Flow, Polling |
| Testing (Backend) | 3-4h | SSH/VPN Mocking kompliziert |
| Testing (Frontend) | 2-3h | Multi-Stage State Testing |
| Security Polish | 3-4h | Encryption, Audit Logging |
| **Total** | **22-29h** | Verteilbar auf 3-4 Tage |

