import hashlib,re
from dataclasses import dataclass,field
from app.models import RouteIn
HEADER=re.compile(r'^\s*\[([^]]+)]');START=re.compile(r'^\s*exten\s*=>\s*([^,]+),1,(.*)$',re.I);DIAL=re.compile(r'Dial\(PJSIP/(?:\$\{EXTEN}|([^@)]+))@([^,)]+)(?:,(\d+))?\)',re.I)
@dataclass
class Context:name:str|None;lines:list[str]=field(default_factory=list)
class DialplanDocument:
    def __init__(self,text):
        self.trailing=text.endswith('\n');self.contexts=[];cur=Context(None,[])
        for line in text.splitlines():
            m=HEADER.match(line)
            if m:self.contexts.append(cur);cur=Context(m.group(1),[line])
            else:cur.lines.append(line)
        self.contexts.append(cur)
    def render(self):
        s='\n'.join(x for c in self.contexts for x in c.lines);return s+('\n' if self.trailing and not s.endswith('\n') else '')
    def names(self):return [c.name for c in self.contexts if c.name]
    def add_context(self,n):
        if n in self.names():raise ValueError('Context already exists')
        self.contexts.append(Context(n,['',f'[{n}]']))
    def delete_context(self,n):self.contexts=[c for c in self.contexts if c.name!=n]
    @staticmethod
    def _id(c,p):return hashlib.sha256(f'{c}\0{p}'.encode()).hexdigest()[:16]
    def routes(self):
        out=[]
        for c in self.contexts:
            starts=[i for i,x in enumerate(c.lines) if START.match(x)]
            for pos,i in enumerate(starts):
                chunk=c.lines[i:(starts[pos+1] if pos+1<len(starts) else len(c.lines))];m=START.match(chunk[0]);joined='\n'.join(chunk);dial=DIAL.search(joined);caller=re.search(r'Set\(CALLERID\(num\)=([^)]*)\)',joined,re.I);play=re.search(r'Playback\(([^)]*)\)',joined,re.I)
                out.append({'route_id':self._id(c.name,m.group(1)),'context':c.name,'pattern':m.group(1),'destination':dial.group(2) if dial else None,'extension':dial.group(1) if dial else None,'timeout':int(dial.group(3) or 60) if dial else 60,'caller_id':caller.group(1) if caller else '','playback':play.group(1) if play else '','description':m.group(2),'record':'MixMonitor(' in joined})
        return out
    def put_route(self,d:RouteIn,old_id=None):
        if d.context not in self.names():self.add_context(d.context)
        if old_id:self.delete_route(old_id)
        c=next(x for x in self.contexts if x.name==d.context);lines=['',f'exten => {d.pattern},1,NoOp({d.description or "Managed route"})']
        if d.caller_id:lines.append(f' same => n,Set(CALLERID(num)={d.caller_id})')
        if d.record:lines+=[' same => n,Set(CALLFILENAME=${CALLERID(num)}-${EXTEN}-${STRFTIME(${EPOCH},,%Y%m%d-%H%M%S)})',' same => n,MixMonitor(/var/spool/asterisk/monitor/${CALLFILENAME}.wav,br)']
        if d.playback:lines+=[' same => n,Answer()',f' same => n,Playback({d.playback})']
        if d.destination:lines.append(f' same => n,Dial(PJSIP/${{EXTEN}}@{d.destination},{d.timeout})')
        elif d.extension:lines.append(f' same => n,Dial(PJSIP/{d.extension},{d.timeout})')
        lines.append(' same => n,Hangup()');c.lines.extend(lines)
    def delete_route(self,rid):
        for c in self.contexts:
            starts=[i for i,x in enumerate(c.lines) if START.match(x)]
            for pos,i in reversed(list(enumerate(starts))):
                m=START.match(c.lines[i]);end=starts[pos+1] if pos+1<len(starts) else len(c.lines)
                if self._id(c.name,m.group(1))==rid:del c.lines[i:end];return
        raise ValueError('Route not found')
def parse_dialplan(t):return DialplanDocument(t)
