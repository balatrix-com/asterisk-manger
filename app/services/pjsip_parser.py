import re
from dataclasses import dataclass,field
from app.models import ExtensionIn,DestinationIn
HEADER=re.compile(r'^\s*\[([^]]+)]\s*(?:;.*)?$');KV=re.compile(r'^\s*([^;=\s]+)\s*=\s*([^;]*?)(?:\s*;.*)?$')
@dataclass
class Block:
    name:str|None;lines:list[str]=field(default_factory=list);values:dict[str,str]=field(default_factory=dict)
    @property
    def type(self):return self.values.get('type','').strip()
class PJSIPDocument:
    def __init__(self,text):
        self.trailing=text.endswith('\n');self.blocks=[];cur=Block(None,[])
        for line in text.splitlines():
            m=HEADER.match(line)
            if m:self.blocks.append(cur);cur=Block(m.group(1),[line])
            else:cur.lines.append(line)
        self.blocks.append(cur);self._refresh()
    def _refresh(self):
        for b in self.blocks:
            b.values={}
            for line in (b.lines[1:] if b.name else b.lines):
                m=KV.match(line)
                if m:b.values[m.group(1).lower()]=m.group(2).strip()
    def render(self):
        s='\n'.join(x for b in self.blocks for x in b.lines);return s+('\n' if self.trailing and not s.endswith('\n') else '')
    def typed(self,n,t):return next((b for b in self.blocks if b.name==n and b.type==t),None)
    def remove_group(self,names):self.blocks=[b for b in self.blocks if b.name not in names]
    def append(self,n,values):
        if self.blocks and self.blocks[-1].lines and any(x.strip() for x in self.blocks[-1].lines):self.blocks.append(Block(None,['']))
        self.blocks.append(Block(n,[f'[{n}]']+[f'{k}={v}' for k,v in values.items() if v!='']));self._refresh()
    def extensions(self,include_password=False):
        out=[]
        for ep in self.blocks:
            if ep.type!='endpoint' or not ep.name or not ep.name.isdigit():continue
            auth=self.typed(ep.values.get('auth',f'auth{ep.name}'),'auth');aor=self.typed(ep.values.get('aors',ep.name),'aor')
            row={'extension':ep.name,'username':auth.values.get('username','') if auth else '','has_password':bool(auth and auth.values.get('password')),'context':ep.values.get('context',''),'caller_id':ep.values.get('callerid',''),'codecs':[x.strip() for x in ep.values.get('allow','').split(',') if x.strip()],'max_contacts':int((aor.values.get('max_contacts','1') if aor else '1').strip()),**{k:ep.values.get(k,'no').rstrip('.')=='yes' for k in ('direct_media','rtp_symmetric','force_rport','rewrite_contact')}}
            if include_password:row['password']=auth.values.get('password','') if auth else ''
            out.append(row)
        return out
    def destinations(self):
        out=[]
        for ep in self.blocks:
            if ep.type!='endpoint' or not ep.name or ep.name.isdigit():continue
            aor=self.typed(ep.values.get('aors',ep.name),'aor');ident=self.typed(ep.name,'identify');contact=(aor.values.get('contact','') if aor else '').removeprefix('sip:');host,_,port=contact.rpartition(':')
            out.append({'name':ep.name,'host':host or contact,'port':int(port) if port.isdigit() else 5060,'context':ep.values.get('context',''),'transport':ep.values.get('transport',''),'codecs':[x.strip() for x in ep.values.get('allow','').split(',') if x.strip()],'identify_match':ident.values.get('match','') if ident else '',**{k:ep.values.get(k,'no').rstrip('.')=='yes' for k in ('direct_media','rtp_symmetric','force_rport','rewrite_contact')}})
        return out
    def put_extension(self,d:ExtensionIn,old=None):
        if old!=d.extension and any(x['extension']==d.extension for x in self.extensions()):raise ValueError('Duplicate extension number')
        existing=next((x for x in self.extensions(True) if x['extension']==old),None);password=d.password or (existing or {}).get('password')
        if not password:raise ValueError('Password is required for a new extension')
        if old:self.remove_group({old,f'auth{old}'})
        self.append(d.extension,{'type':'endpoint','context':d.context,'disallow':'all','allow':','.join(d.codecs),'auth':f'auth{d.extension}','aors':d.extension,'direct_media':yn(d.direct_media),'rtp_symmetric':yn(d.rtp_symmetric),'force_rport':yn(d.force_rport),'rewrite_contact':yn(d.rewrite_contact),'callerid':d.caller_id})
        self.append(f'auth{d.extension}',{'type':'auth','auth_type':'userpass','username':d.username,'password':password});self.append(d.extension,{'type':'aor','max_contacts':str(d.max_contacts)})
    def delete_extension(self,e):self.remove_group({e,f'auth{e}'})
    def put_destination(self,d:DestinationIn,old=None):
        if old!=d.name and any(x['name']==d.name for x in self.destinations()):raise ValueError('Duplicate destination name')
        if old:self.remove_group({old})
        self.append(d.name,{'type':'endpoint','context':d.context,'disallow':'all','allow':','.join(d.codecs),'aors':d.name,'transport':d.transport,'direct_media':yn(d.direct_media),'rtp_symmetric':yn(d.rtp_symmetric),'force_rport':yn(d.force_rport),'rewrite_contact':yn(d.rewrite_contact)});self.append(d.name,{'type':'aor','contact':f'sip:{d.host}:{d.port}'});self.append(d.name,{'type':'identify','endpoint':d.name,'match':d.identify_match or d.host})
    def delete_destination(self,n):self.remove_group({n})
def yn(v):return 'yes' if v else 'no'
def parse_pjsip(t):return PJSIPDocument(t)
