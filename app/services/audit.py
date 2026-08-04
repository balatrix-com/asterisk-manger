import json
from datetime import datetime,timezone
class AuditLog:
    def __init__(self,p):self.path=p
    def write(self,user,action,detail=''):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open('a',encoding='utf-8') as f:f.write(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'user':user,'action':action,'detail':detail[:500]},separators=(',',':'))+'\n')
    def recent(self,limit=20):
        if not self.path.exists():return []
        return [json.loads(x) for x in self.path.read_text(encoding='utf-8').splitlines()[-limit:]][::-1]
