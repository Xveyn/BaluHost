# Cloud Import einrichten

## Voraussetzungen

Bevor du Dateien von Google Drive oder OneDrive importieren kannst, musst du eine OAuth-Verbindung mit dem jeweiligen Cloud-Anbieter einrichten. Dafür benötigst du:

1. Ein **Google Cloud**- oder **Microsoft Azure**-Konto (kostenlos)
2. OAuth-Credentials (Client ID + Client Secret) vom Anbieter
3. Eine gueltige **Redirect-URI** in der Anbieter-Konsole

---

## Google Drive einrichten

### Schritt 1: Google Cloud Projekt erstellen

1. Gehe zur [Google Cloud Console](https://console.cloud.google.com)
2. Erstelle ein neues Projekt (oder verwende ein bestehendes)
3. Aktiviere die **Google Drive API**:
   - Navigation: APIs & Services > Library
   - Suche nach "Google Drive API" und aktiviere sie

### Schritt 2: OAuth-Credentials erstellen

1. Gehe zu **APIs & Services > Credentials**
2. Klicke auf **"+ Create Credentials" > "OAuth client ID"**
3. Waehle **"Web application"** als Anwendungstyp
4. Vergib einen Namen (z.B. "BaluHost")
5. Unter **"Authorized redirect URIs"** fuege hinzu:
   ```
   https://<dein-domain>/api/cloud/oauth/callback
   ```

> **Wichtig:** Google akzeptiert **keine** `.local`-Domains und **keine** IP-Adressen als Redirect-URI. Du benoetigst eine Domain mit oeffentlicher TLD (z.B. `.org`, `.com`, `.net`).
>
> **Empfehlung:** Nutze einen kostenlosen DNS-Dienst wie [DuckDNS](https://www.duckdns.org):
> 1. Erstelle dort eine Subdomain (z.B. `meinnas.duckdns.org`)
> 2. Trage deine **lokale NAS-IP** ein (z.B. `192.168.178.20`)
> 3. Verwende `https://meinnas.duckdns.org/api/cloud/oauth/callback` als Redirect-URI
> 4. Fuege auf deinem PC in der Hosts-Datei (`C:\Windows\System32\drivers\etc\hosts`) den Eintrag hinzu:
>    ```
>    192.168.178.20 meinnas.duckdns.org
>    ```
> 5. Setze auf dem NAS die Umgebungsvariable `PUBLIC_URL=https://meinnas.duckdns.org`

6. Klicke auf **"Create"**
7. Kopiere die **Client ID** und das **Client Secret**

### Schritt 3: OAuth-Consent-Screen konfigurieren

1. Gehe zu **APIs & Services > OAuth consent screen**
2. Waehle **"External"** als User Type
3. Fuege die erforderlichen Angaben ein (App-Name, Support-E-Mail)
4. Unter **"Test users"** fuege deine eigene Google-E-Mail-Adresse hinzu (solange die App nicht veroeffentlicht ist, koennen nur Test-User sich anmelden)

### Schritt 4: Credentials in BaluHost eintragen

1. Gehe in BaluHost zu **Settings > Integrations**
2. Klicke bei Google Drive auf **"Configure"**
3. Trage Client ID und Client Secret ein
4. Klicke auf **"Save"**

### Schritt 5: Verbindung herstellen

1. Gehe zu **Cloud Import** (Seitenleiste)
2. Klicke auf **"Connect"** und waehle Google Drive
3. Du wirst zu Google weitergeleitet — melde dich an und erteile die Berechtigung
4. Nach erfolgreicher Autorisierung wirst du zurueck zu BaluHost geleitet

---

## OneDrive einrichten

### Schritt 1: Azure App registrieren

1. Gehe zum [Azure Portal](https://portal.azure.com) > **Azure Active Directory > App registrations**
2. Klicke auf **"New registration"**
3. Vergib einen Namen (z.B. "BaluHost")
4. Waehle unter **Supported account types** die Option **"Accounts in any organizational directory and personal Microsoft accounts"**
5. Unter **Redirect URI** waehle "Web" und trage ein:
   ```
   https://<dein-domain>/api/cloud/oauth/callback
   ```
6. Klicke auf **"Register"**

### Schritt 2: Client Secret erstellen

1. Gehe zu **Certificates & secrets**
2. Klicke auf **"New client secret"**
3. Vergib eine Beschreibung und waehle eine Laufzeit
4. Kopiere den **Value** (wird nur einmal angezeigt!)

### Schritt 3: Credentials in BaluHost eintragen

1. Gehe in BaluHost zu **Settings > Integrations**
2. Klicke bei OneDrive auf **"Configure"**
3. Trage die **Application (client) ID** und das **Client Secret** ein
4. Klicke auf **"Save"**

### Schritt 4: Verbindung herstellen

Gleicher Ablauf wie bei Google Drive — ueber Cloud Import verbinden.

---

## Dateien importieren

Nach erfolgreicher Verbindung:

1. Gehe zu **Cloud Import**
2. Waehle die gewuenschte Verbindung
3. Durchsuche deine Cloud-Dateien
4. Waehle Dateien/Ordner zum Import aus
5. Waehle den Zielordner auf dem NAS
6. Starte den Import — der Fortschritt wird in Echtzeit angezeigt

---

## Haeufige Probleme

### "redirect_uri_mismatch" Fehler

Die Redirect-URI in der Cloud-Konsole stimmt nicht exakt mit der URI ueberein, die BaluHost generiert. Pruefe:

- Stimmt das Protokoll? (`http` vs `https`)
- Stimmt die Domain exakt? (inkl. Port, falls vorhanden)
- Ist die `PUBLIC_URL` Umgebungsvariable auf dem NAS korrekt gesetzt?
- Hast du nach dem Aendern das Backend neu gestartet?

### "Server nicht gefunden" nach Google-Login

Dein Browser kann die Domain nicht aufloesen. Pruefe:

- Ist die Domain (z.B. DuckDNS) auf die richtige lokale IP gesetzt?
- Ist ein Eintrag in der Hosts-Datei deines PCs vorhanden?
- Fuehre `ipconfig /flushdns` (Windows) oder `sudo dscacheutil -flushcache` (macOS) aus

### Google zeigt "Zugriff blockiert"

- Pruefe ob deine E-Mail als **Test User** im OAuth Consent Screen eingetragen ist
- Oder veroeffentliche die App (erfordert Google-Verifizierung)

### Verbindung kann nicht geloescht werden

Falls ein 500-Fehler beim Loeschen auftritt, starte das Backend neu und versuche es erneut.
