import hashlib,os,tempfile
try:import pwd,grp
except ImportError:pwd=grp=None
class VersionConflict(Exception):pass
def version(b):return hashlib.sha256(b).hexdigest()
class FileManager:
    def __init__(self,s):self.settings=s
    def read(self,n):
        p=self.settings.config_path(n);raw=p.read_bytes();st=p.stat();return {'file':n,'content':raw.decode(),'version':version(raw),'modified_at':st.st_mtime}
    def atomic_write(self,n,content,expected):
        p=self.settings.config_path(n);current=p.read_bytes()
        if version(current)!=expected:raise VersionConflict('File changed since it was loaded')
        fd,tmp=tempfile.mkstemp(prefix=f'.{p.name}.',dir=p.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:f.write(content);f.flush();os.fsync(f.fileno())
            if pwd is not None:os.chown(tmp,pwd.getpwnam(self.settings.file_owner).pw_uid,grp.getgrnam(self.settings.file_group).gr_gid)
            os.chmod(tmp,int(self.settings.file_mode,8));os.replace(tmp,p)
            try:
                d=os.open(p.parent,os.O_DIRECTORY);os.fsync(d);os.close(d)
            except (AttributeError,OSError):pass
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        return self.read(n)
