import secrets,sys
from pwdlib import PasswordHash
from fastapi import HTTPException,Request
hasher=PasswordHash.recommended()
def hash_password(p): return hasher.hash(p)
def verify_password(p,h):
    try:return bool(h) and hasher.verify(p,h)
    except Exception:return False
def csrf_token(request):
    token=request.session.get('csrf')
    if not token: token=secrets.token_urlsafe(32);request.session['csrf']=token
    return token
def require_user(request:Request):
    if not request.session.get('user'): raise HTTPException(401,'Authentication required')
    return request.session['user']
def require_csrf(request):
    if not secrets.compare_digest(request.headers.get('x-csrf-token',''),request.session.get('csrf','')): raise HTTPException(403,'Invalid CSRF token')
if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: python -m app.security PASSWORD')
    print(hash_password(sys.argv[1]))
