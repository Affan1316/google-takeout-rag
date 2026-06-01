import sqlite3, shutil, tempfile, os
from datetime import datetime, timedelta

base = os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data')
profiles = ['Guest Profile','Profile 1','Profile 11','Profile 12','Profile 13','Profile 14','Profile 16','Profile 17','Profile 4','Profile 5','Profile 7']

for p in profiles:
    hist = os.path.join(base, p, 'History')
    if not os.path.exists(hist):
        continue
    tmp = os.path.join(tempfile.mkdtemp(), 'H')
    shutil.copy2(hist, tmp)
    conn = sqlite3.connect(tmp)
    try:
        r = conn.execute("SELECT COUNT(*) FROM urls WHERE url LIKE '%grok%'").fetchone()[0]
        if r > 0:
            print(f'{p}: {r} grok URLs found!')
            rows = conn.execute("SELECT url, title FROM urls WHERE url LIKE '%grok%' LIMIT 5").fetchall()
            for url, title in rows:
                print(f'  {title[:60]}  |  {url[:80]}')
        else:
            print(f'{p}: no grok URLs')
    except Exception as e:
        print(f'{p}: error - {e}')
    conn.close()
    os.remove(tmp)
