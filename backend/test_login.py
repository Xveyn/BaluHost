import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

data = json.dumps({'username':'admin','password':'changeme'}).encode()
req = urllib.request.Request(
    'https://localhost:8000/api/auth/login', 
    data=data, 
    headers={'Content-Type':'application/json'}
)

try:
    resp = urllib.request.urlopen(req, context=ctx)
    print('Status:', resp.status)
    print('Body:', resp.read().decode())
except urllib.error.HTTPError as e:
    print('HTTP Error:', e.code)
    print('Body:', e.read().decode())
except Exception as e:
    print('Error:', e)
    import traceback
    traceback.print_exc()
