import json, time, sys
sys.path.insert(0, '/TiktokUploader')
with open('/TiktokUploader/TK_cookies_nuggerchicken433.json') as f:
    cookies = json.load(f)
now = int(time.time())
print("Current time:", now)
for c in cookies:
    name = c.get('name', '')
    if name in ['sessionid', 'sid_tt', 'sessionid_ss', 'passport_auth_status']:
        exp = c.get('expires') or c.get('expirationDate', 0)
        if exp:
            days = (int(exp) - now) // 86400
            status = 'EXPIRED' if int(exp) < now else ('valid (%d days left)' % days)
        else:
            status = 'no expiry set'
        print(name + ' : ' + status)
