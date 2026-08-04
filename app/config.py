from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file='.env',extra='ignore')
    pjsip_config_path:Path=Path('/etc/asterisk/pjsip.conf')
    extensions_config_path:Path=Path('/etc/asterisk/extensions.conf')
    backup_directory:Path=Path('/var/backups/asterisk-config-manager')
    asterisk_binary:Path=Path('/usr/sbin/asterisk')
    asterisk_service_name:str='asterisk'
    secret_key:str='development-only-change-this-secret'
    admin_username:str='admin'; admin_password_hash:str=''; session_ttl_seconds:int=1800
    file_owner:str='asterisk'; file_group:str='asterisk'; file_mode:str='0640'
    audit_log_path:Path=Path('/var/log/asterisk-config-manager/audit.jsonl')
    def config_path(self,name):
        if name=='pjsip': return self.pjsip_config_path
        if name=='extensions': return self.extensions_config_path
        raise ValueError('Unknown configuration file')
@lru_cache
def get_settings(): return Settings()
