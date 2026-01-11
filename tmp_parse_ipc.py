import subprocess, re, json, sys
exe = r"F:/Programme (x86)/Baluhost/baludesk/backend/build/Release/baludesk-backend.exe"
payload = b'{"type":"get_system_info","id":123}\n'
try:
    p = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.communicate(payload, timeout=15)[0].decode('utf-8', errors='ignore')
    # Find the JSON object with type":"system_info"
    m = re.search(r'(\{\s*"type"\s*:\s*"system_info"[\s\S]*?\})', out)
    if not m:
        print('Could not find system_info JSON in output')
        print(out)
        sys.exit(1)
    js = m.group(1)
    obj = json.loads(js)
    print(json.dumps(obj, indent=2))
    if 'data' in obj:
        print('\nData keys:', list(obj['data'].keys()))
        print('data.uptime =', obj['data'].get('uptime'))
        print('data.serverUptime =', obj['data'].get('serverUptime'))
except subprocess.TimeoutExpired:
    p.kill()
    print('Process timed out')
except Exception as e:
    print('ERROR', e)
