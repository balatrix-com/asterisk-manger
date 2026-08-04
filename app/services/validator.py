import ipaddress,re
from app.services.pjsip_parser import parse_pjsip
from app.services.dialplan_parser import parse_dialplan
HOST=re.compile(r'^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$')
def valid_host(v):
    try:ipaddress.ip_address(v);return True
    except ValueError:return bool(HOST.fullmatch(v))
def validate_configs(pt,dt):
    errors=[];warnings=[]
    try:p=parse_pjsip(pt);extensions=p.extensions();destinations=p.destinations()
    except Exception as e:return {'valid':False,'errors':[f'PJSIP parse error: {e}'],'warnings':[]}
    try:d=parse_dialplan(dt);routes=d.routes()
    except Exception as e:return {'valid':False,'errors':[f'Dialplan parse error: {e}'],'warnings':[]}
    ids=[x['extension'] for x in extensions]
    if len(ids)!=len(set(ids)):errors.append('Duplicate extension numbers')
    dests={x['name'] for x in destinations};contexts=set(d.names())
    for x in destinations:
        if not valid_host(x['host']):errors.append(f"Invalid host for destination {x['name']}")
    for x in extensions+destinations:
        if x.get('context') and x['context'] not in contexts:warnings.append(f"PJSIP context {x['context']} does not exist in extensions.conf")
    for r in routes:
        if r['destination'] and r['destination'] not in dests:errors.append(f"Route {r['route_id']} refers to missing destination {r['destination']}")
    return {'valid':not errors,'errors':errors,'warnings':sorted(set(warnings))}
