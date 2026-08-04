from types import SimpleNamespace
from app.models import ExtensionIn,DestinationIn,RouteIn
from app.services.pjsip_parser import parse_pjsip
from app.services.dialplan_parser import parse_dialplan
from app.services.validator import validate_configs
from app.services.file_manager import FileManager,VersionConflict
P=''';comment
[101]
type=endpoint
context=internal
allow=ulaw
auth=auth101
aors=101
[auth101]
type=auth
username=101
password=secret
[101]
type=aor
max_contacts=1
[trunk]
type=endpoint
context=from-trunk
aors=trunk
[trunk]
type=aor
contact=sip:192.0.2.1:5060
[trunk]
type=identify
endpoint=trunk
match=192.0.2.1
'''
D='''[internal]
exten => _X.,1,NoOp(Test)
 same => n,Dial(PJSIP/${EXTEN}@trunk,30)
[from-trunk]
exten => _X.,1,Playback(demo-congratulations)
'''
def test_repeated_and_hidden_password():
 p=parse_pjsip(P);assert len([b for b in p.blocks if b.name=='101'])==2;assert 'password' not in p.extensions()[0]
def test_extension_destination_and_comment():
 p=parse_pjsip(P);p.put_extension(ExtensionIn(extension='102',username='102',password='strong',context='internal'));p.put_destination(DestinationIn(name='sbc',host='sbc.example.com',context='internal'));assert ';comment' in p.render();assert len(p.extensions())==2
def test_duplicate():
 p=parse_pjsip(P)
 try:p.put_extension(ExtensionIn(extension='101',username='x',password='strong',context='internal'))
 except ValueError:return
 assert False
def test_route_and_missing_trunk():
 d=parse_dialplan(D);r=d.routes()[0];d.put_route(RouteIn(context='internal',destination='trunk',description='new'),r['route_id']);assert d.routes()[0]['destination']=='trunk';assert not validate_configs(P,D.replace('@trunk','@missing'))['valid']
def test_conflict_and_atomic(tmp_path):
 p=tmp_path/'pjsip.conf';e=tmp_path/'extensions.conf';p.write_text('old');e.write_text('dial');s=SimpleNamespace(config_path=lambda n:p if n=='pjsip' else e,file_mode='0640',file_owner='nobody',file_group='nogroup');f=FileManager(s);v=f.read('pjsip')['version'];f.atomic_write('pjsip','new',v);assert p.read_text()=='new'
 try:f.atomic_write('pjsip','bad',v)
 except VersionConflict:return
 assert False
