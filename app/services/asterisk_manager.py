import subprocess
class AsteriskManager:
    COMMANDS={'pjsip':['-rx','pjsip reload'],'dialplan':['-rx','dialplan reload']}
    def __init__(self,s):self.binary=str(s.asterisk_binary)
    def run(self,target):
        output=[]
        for item in (['pjsip','dialplan'] if target=='all' else [target]):
            if item not in self.COMMANDS:raise ValueError('Unsupported reload target')
            try:p=subprocess.run([self.binary,*self.COMMANDS[item]],capture_output=True,text=True,timeout=30,check=False)
            except Exception as e:return {'ok':False,'output':str(e)}
            output.append((p.stdout+p.stderr).strip())
            if p.returncode:return {'ok':False,'output':'\n'.join(output)}
        return {'ok':True,'output':'\n'.join(output)}
    def status(self):
        try:
            p=subprocess.run([self.binary,'-rx','core show uptime'],capture_output=True,text=True,timeout=5,check=False);return {'connected':p.returncode==0,'detail':(p.stdout+p.stderr).strip()}
        except Exception as e:return {'connected':False,'detail':str(e)}
