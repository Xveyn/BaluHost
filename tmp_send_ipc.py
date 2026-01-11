import subprocess
import sys
exe = r"F:/Programme (x86)/Baluhost/baludesk/backend/build/Release/baludesk-backend.exe"
payload = b'{"type":"get_system_info","id":123}\n'
try:
    p = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        out = p.communicate(payload, timeout=8)[0].decode('utf-8', errors='ignore')
    except subprocess.TimeoutExpired:
        p.kill()
        out = p.communicate()[0].decode('utf-8', errors='ignore')
    # Try to extract the system_info JSON
    import re, json
    m = re.search(r'(\{\s*"type"\s*:\s*"system_info"[\s\S]*?\})', out)
    if m:
        js = m.group(1)
        try:
            obj = json.loads(js)
            print(json.dumps(obj, indent=2))
            if 'data' in obj:
                print('\nData keys:', list(obj['data'].keys()))
                print('data.uptime =', obj['data'].get('uptime'))
                print('data.serverUptime =', obj['data'].get('serverUptime'))
        except Exception:
            sys.stdout.write(out)
    else:
        sys.stdout.write(out)
except Exception as e:
    print(f"ERROR: {e}")
