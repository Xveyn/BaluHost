# Fritz!Box TR-064 Wake-on-LAN Protocol

This document describes how to send Wake-on-LAN via a Fritz!Box router's TR-064 SOAP API.
The BaluApp can use this to wake the NAS directly when the NAS backend is unreachable.

## Endpoint

- **URL**: `http://<fritzbox-ip>:49000/upnp/control/hosts`
- **Method**: POST
- **Auth**: HTTP Digest Authentication
- **Content-Type**: `text/xml; charset="utf-8"`

Port 49000 is the default TR-064 HTTP port. Some Fritz!Box models support HTTPS on port 49443.

## SOAP Envelope

```xml
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:X_AVM-DE_WakeOnLANByMACAddress xmlns:u="urn:dslforum-org:service:Hosts:1">
      <NewMACAddress>AA:BB:CC:DD:EE:FF</NewMACAddress>
    </u:X_AVM-DE_WakeOnLANByMACAddress>
  </s:Body>
</s:Envelope>
```

## Required Header

```
SOAPAction: "urn:dslforum-org:service:Hosts:1#X_AVM-DE_WakeOnLANByMACAddress"
```

## Authentication

Fritz!Box uses HTTP Digest Authentication (RFC 7616).

- **Username**: Often empty on Fritz!Box (just `""`)
- **Password**: The Fritz!Box admin password or a dedicated TR-064 user password
- Empty username is valid and common — the auth library must support this

## Example: cURL

```bash
curl -s --digest --user ":MyPassword" \
  -H 'Content-Type: text/xml; charset="utf-8"' \
  -H 'SOAPAction: "urn:dslforum-org:service:Hosts:1#X_AVM-DE_WakeOnLANByMACAddress"' \
  -d '<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:X_AVM-DE_WakeOnLANByMACAddress xmlns:u="urn:dslforum-org:service:Hosts:1">
      <NewMACAddress>AA:BB:CC:DD:EE:FF</NewMACAddress>
    </u:X_AVM-DE_WakeOnLANByMACAddress>
  </s:Body>
</s:Envelope>' \
  http://192.168.178.1:49000/upnp/control/hosts
```

Note: `--user ":MyPassword"` — the colon before the password means empty username.

## Example: Kotlin (BaluApp)

```kotlin
import okhttp3.Credentials
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

suspend fun sendFritzBoxWol(
    host: String,
    port: Int = 49000,
    username: String = "",
    password: String,
    macAddress: String,
): Boolean {
    val url = "http://$host:$port/upnp/control/hosts"
    val soapBody = """
        <?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
                    s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
          <s:Body>
            <u:X_AVM-DE_WakeOnLANByMACAddress
              xmlns:u="urn:dslforum-org:service:Hosts:1">
              <NewMACAddress>$macAddress</NewMACAddress>
            </u:X_AVM-DE_WakeOnLANByMACAddress>
          </s:Body>
        </s:Envelope>
    """.trimIndent()

    // OkHttp handles Digest Auth via Authenticator
    val client = OkHttpClient.Builder()
        .authenticator { _, response ->
            val credential = Credentials.basic(username, password)
            response.request.newBuilder()
                .header("Authorization", credential)
                .build()
        }
        .build()

    val request = Request.Builder()
        .url(url)
        .post(soapBody.toRequestBody("text/xml; charset=utf-8".toMediaType()))
        .header("SOAPAction",
            "\"urn:dslforum-org:service:Hosts:1#X_AVM-DE_WakeOnLANByMACAddress\"")
        .build()

    return withContext(Dispatchers.IO) {
        val response = client.newCall(request).execute()
        response.isSuccessful
    }
}
```

**Note for BaluApp implementation**: Use OkHttp's `DigestAuthenticator` or a dedicated Digest Auth library instead of Basic Auth — the example above is simplified. Fritz!Box requires Digest Auth.

## Credential Storage

The BaluApp should:
1. Prompt the user once for Fritz!Box credentials (host, port, username, password)
2. Store them encrypted locally (Android Keystore / EncryptedSharedPreferences)
3. Reuse for subsequent WoL calls without re-prompting
4. Allow the user to update credentials in settings

## Connection Test

To verify connectivity, fetch the service description:

```
GET http://<host>:<port>/hostsSCPD.xml
```

A 200 response confirms the TR-064 service is available. A 401 means credentials are wrong.

## Error Handling

| HTTP Code | Meaning |
|-----------|---------|
| 200 | Success (check body for SOAP fault) |
| 401 | Authentication failed |
| Connection refused | Fritz!Box not reachable on this host:port |
| Timeout | Fritz!Box not responding |

SOAP faults appear inside the 200 response body as `<s:Fault>` elements. Parse the `<faultstring>` for the error message.
