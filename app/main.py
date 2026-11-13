import difflib,time
from pathlib import Path
from fastapi import Depends,FastAPI,Form,HTTPException,Request
from fastapi.responses import JSONResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from app.config import get_settings
from app.models import ExtensionIn,DestinationIn,ContextIn,RouteIn,SaveRequest,ReloadRequest
from app.security import verify_password,require_user,require_csrf,csrf_token
from app.services.pjsip_parser import parse_pjsip
from app.services.dialplan_parser import parse_dialplan
from app.services.validator import validate_configs
from app.services.file_manager import FileManager,VersionConflict
from app.services.backup_manager import BackupManager
from app.services.asterisk_manager import AsteriskManager
from app.services.audit import AuditLog
from app.services.call_dialer import CallDialer,Target
BASE=Path(__file__).parent;s=get_settings();app=FastAPI(title='Asterisk Config Manager',docs_url=None,redoc_url=None)
app.add_middleware(SessionMiddleware,secret_key=s.secret_key,max_age=s.session_ttl_seconds,https_only=True,same_site='strict');app.mount('/static',StaticFiles(directory=BASE/'static'),name='static');templates=Jinja2Templates(directory=BASE/'templates')
files=FileManager(s);backups=BackupManager(s);asterisk=AsteriskManager(s);audit=AuditLog(s.audit_log_path);state={'last_reload':None,'last_reload_ok':None,'last_reload_output':''}
dialer=CallDialer(s)
@app.on_event('shutdown')
def stop_dialer_on_shutdown():
    try:dialer.stop()
    except (RuntimeError,OSError,TimeoutError,PermissionError,ConnectionError):pass
@app.exception_handler(VersionConflict)
async def conflict(_,e):return JSONResponse({'detail':str(e)},409)
@app.exception_handler(ValueError)
async def value_error(_,e):return JSONResponse({'detail':str(e)},422)
@app.get('/')
def index(request:Request):
    logged=bool(request.session.get('user'));return templates.TemplateResponse(request,'index.html',{'logged_in':logged,'csrf':csrf_token(request) if logged else '','error':None})
@app.post('/login')
def login(request:Request,username:str=Form(...),password:str=Form(...)):
    if username!=s.admin_username or not verify_password(password,s.admin_password_hash):return templates.TemplateResponse(request,'index.html',{'logged_in':False,'csrf':'','error':'Invalid credentials'},status_code=401)
    request.session.clear();request.session['user']=username;csrf_token(request);audit.write(username,'login');return RedirectResponse('/',303)
@app.post('/logout')
def logout(request:Request):require_csrf(request);request.session.clear();return {'ok':True}
def snapshot():return files.read('pjsip'),files.read('extensions')
def commit(name,content,expected,user,reload=False):
    p,e=snapshot();validation=validate_configs(content if name=='pjsip' else p['content'],content if name=='extensions' else e['content'])
    if not validation['valid']:raise HTTPException(422,detail=validation)
    bid=backups.create(name,s.config_path(name),expected);saved=files.atomic_write(name,content,expected);rr=None
    if reload:
        rr=asterisk.run('pjsip' if name=='pjsip' else 'dialplan');state.update(last_reload=time.time(),last_reload_ok=rr['ok'],last_reload_output=rr['output'])
        if not rr['ok']:files.atomic_write(name,backups.content(bid),saved['version']);raise HTTPException(500,detail={'message':'Reload failed; previous configuration restored','output':rr['output']})
    audit.write(user,'save',f'{name}; backup={bid}; reload={reload}');return {'file':saved,'validation':validation,'backup':bid,'reload':rr}
@app.get('/api/config')
def config(user=Depends(require_user)):p,e=snapshot();return {'pjsip':p,'extensions':e}
@app.get('/api/status')
def status(user=Depends(require_user)):
    p,e=snapshot();pp=parse_pjsip(p['content']);dd=parse_dialplan(e['content']);return {'asterisk':asterisk.status(),'counts':{'extensions':len(pp.extensions()),'destinations':len(pp.destinations()),'contexts':len(dd.names())},'files':{'pjsip':p,'extensions':e},'validation':validate_configs(p['content'],e['content']),'recent_changes':audit.recent(),**state}
@app.get('/api/extensions')
def extensions(user=Depends(require_user)):return parse_pjsip(files.read('pjsip')['content']).extensions()
@app.post('/api/extensions')
def extension_add(data:ExtensionIn,request:Request,user=Depends(require_user)):require_csrf(request);c=files.read('pjsip');d=parse_pjsip(c['content']);d.put_extension(data);return commit('pjsip',d.render(),c['version'],user)
@app.put('/api/extensions/{ext}')
def extension_edit(ext:str,data:ExtensionIn,request:Request,user=Depends(require_user)):require_csrf(request);c=files.read('pjsip');d=parse_pjsip(c['content']);d.put_extension(data,ext);return commit('pjsip',d.render(),c['version'],user)
@app.delete('/api/extensions/{ext}')
def extension_delete(ext:str,request:Request,user=Depends(require_user)):require_csrf(request);c=files.read('pjsip');d=parse_pjsip(c['content']);d.delete_extension(ext);return commit('pjsip',d.render(),c['version'],user)
@app.get('/api/destinations')
def destinations(user=Depends(require_user)):return parse_pjsip(files.read('pjsip')['content']).destinations()
@app.post('/api/destinations')
def dest_add(data:DestinationIn,request:Request,user=Depends(require_user)):require_csrf(request);c=files.read('pjsip');d=parse_pjsip(c['content']);d.put_destination(data);return commit('pjsip',d.render(),c['version'],user)
@app.put('/api/destinations/{name}')
def dest_edit(name:str,data:DestinationIn,request:Request,user=Depends(require_user)):require_csrf(request);c=files.read('pjsip');d=parse_pjsip(c['content']);d.put_destination(data,name);return commit('pjsip',d.render(),c['version'],user)
@app.delete('/api/destinations/{name}')
def dest_delete(name:str,request:Request,user=Depends(require_user)):require_csrf(request);c=files.read('pjsip');d=parse_pjsip(c['content']);d.delete_destination(name);return commit('pjsip',d.render(),c['version'],user)
@app.get('/api/dialplan')
def dialplan(user=Depends(require_user)):d=parse_dialplan(files.read('extensions')['content']);return {'contexts':d.names(),'routes':d.routes()}
@app.post('/api/dialplan/contexts')
def context_add(data:ContextIn,request:Request,user=Depends(require_user)):require_csrf(request);c=files.read('extensions');d=parse_dialplan(c['content']);d.add_context(data.name);return commit('extensions',d.render(),c['version'],user)
@app.delete('/api/dialplan/contexts/{name}')
def context_delete(name:str,request:Request,user=Depends(require_user)):require_csrf(request);c=files.read('extensions');d=parse_dialplan(c['content']);d.delete_context(name);return commit('extensions',d.render(),c['version'],user)
@app.post('/api/dialplan/routes')
def route_add(data:RouteIn,request:Request,user=Depends(require_user)):require_csrf(request);c=files.read('extensions');d=parse_dialplan(c['content']);d.put_route(data);return commit('extensions',d.render(),c['version'],user)
@app.put('/api/dialplan/routes/{rid}')
def route_edit(rid:str,data:RouteIn,request:Request,user=Depends(require_user)):require_csrf(request);c=files.read('extensions');d=parse_dialplan(c['content']);d.put_route(data,rid);return commit('extensions',d.render(),c['version'],user)
@app.delete('/api/dialplan/routes/{rid}')
def route_delete(rid:str,request:Request,user=Depends(require_user)):require_csrf(request);c=files.read('extensions');d=parse_dialplan(c['content']);d.delete_route(rid);return commit('extensions',d.render(),c['version'],user)
@app.post('/api/validate')
def validate(user=Depends(require_user)):p,e=snapshot();return validate_configs(p['content'],e['content'])
@app.post('/api/preview')
def preview(data:SaveRequest,user=Depends(require_user)):
    c=files.read(data.file)
    if c['version']!=data.version:raise VersionConflict('File changed since it was loaded')
    p,e=snapshot();return {'diff':'\n'.join(difflib.unified_diff(c['content'].splitlines(),data.content.splitlines(),fromfile='current',tofile='proposed',lineterm='')),'validation':validate_configs(data.content if data.file=='pjsip' else p['content'],data.content if data.file=='extensions' else e['content'])}
@app.post('/api/save')
def save(data:SaveRequest,request:Request,user=Depends(require_user)):require_csrf(request);return commit(data.file,data.content,data.version,user,data.reload)
@app.post('/api/reload')
def reload(data:ReloadRequest,request:Request,user=Depends(require_user)):require_csrf(request);r=asterisk.run(data.target);state.update(last_reload=time.time(),last_reload_ok=r['ok'],last_reload_output=r['output']);audit.write(user,'reload',data.target);return r
@app.get('/api/backups')
def backup_list(user=Depends(require_user)):return backups.list()
@app.get('/api/backups/{bid}')
def backup_get(bid:str,user=Depends(require_user)):name=bid.split('-')[0];return {'content':backups.content(bid),'diff':backups.diff(bid,files.read(name)['content'])}
@app.post('/api/backups/{bid}/restore')
def backup_restore(bid:str,request:Request,user=Depends(require_user)):require_csrf(request);name=bid.split('-')[0];c=files.read(name);return commit(name,backups.content(bid),c['version'],user)
@app.get('/api/dialer/status')
def dialer_status(user=Depends(require_user)):return dialer.snapshot()
@app.post('/api/dialer/start')
def dialer_start(data:dict,request:Request,user=Depends(require_user)):
    require_csrf(request)
    try:result=dialer.start(Target.parse(data))
    except RuntimeError as exc:raise HTTPException(409,str(exc)) from exc
    audit.write(user,'dialer-start')
    return result
@app.post('/api/dialer/stop')
def dialer_stop(request:Request,user=Depends(require_user)):
    require_csrf(request)
    try:result=dialer.stop()
    except (RuntimeError,OSError,TimeoutError,PermissionError,ConnectionError) as exc:raise HTTPException(503,str(exc)) from exc
    audit.write(user,'dialer-stop')
    return result
