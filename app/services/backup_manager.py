import difflib,re,shutil
from datetime import datetime,timezone
SAFE=re.compile(r'^(pjsip|extensions)-\d{8}T\d{6}\.\d{6}Z-[0-9a-f]{8}\.conf$')
class BackupManager:
    def __init__(self,s):self.settings=s;self.root=s.backup_directory
    def create(self,n,source,v):
        self.root.mkdir(parents=True,exist_ok=True);stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');target=self.root/f'{n}-{stamp}-{v[:8]}.conf';shutil.copy2(source,target);return target.name
    def list(self):
        if not self.root.exists():return []
        return [{'id':p.name,'file':p.name.split('-')[0],'size':p.stat().st_size,'created_at':p.stat().st_mtime} for p in sorted(self.root.glob('*.conf'),reverse=True) if SAFE.fullmatch(p.name)]
    def path(self,b):
        if not SAFE.fullmatch(b):raise ValueError('Invalid backup id')
        p=self.root/b
        if not p.is_file():raise FileNotFoundError(b)
        return p
    def content(self,b):return self.path(b).read_text(encoding='utf-8')
    def diff(self,b,current):return '\n'.join(difflib.unified_diff(self.content(b).splitlines(),current.splitlines(),fromfile=b,tofile='current',lineterm=''))
