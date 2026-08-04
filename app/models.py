import re
from typing import Literal
from pydantic import BaseModel,Field,field_validator
NAME=re.compile(r'^[A-Za-z0-9_.-]{1,64}$'); EXT=re.compile(r'^\d{1,20}$'); CALLER=re.compile(r'^[+0-9]{0,32}$')
class ExtensionIn(BaseModel):
    extension:str; username:str; password:str|None=Field(None,min_length=4,max_length=128); context:str='internal'; caller_id:str=''; codecs:list[str]=['ulaw']; max_contacts:int=Field(1,ge=1,le=100); direct_media:bool=False; rtp_symmetric:bool=True; force_rport:bool=True; rewrite_contact:bool=True
    @field_validator('extension')
    @classmethod
    def ext(cls,v):
        if not EXT.fullmatch(v): raise ValueError('Extension must contain digits only')
        return v
    @field_validator('username','context')
    @classmethod
    def names(cls,v):
        if not NAME.fullmatch(v): raise ValueError('Invalid name')
        return v
    @field_validator('caller_id')
    @classmethod
    def caller(cls,v):
        if not CALLER.fullmatch(v): raise ValueError('Invalid caller ID')
        return v
    @field_validator('codecs')
    @classmethod
    def codecs_ok(cls,v):
        if not v or any(x not in {'ulaw','alaw','g722','gsm','opus','slin','slin16'} for x in v): raise ValueError('Unsupported codec')
        return v
class DestinationIn(BaseModel):
    name:str; host:str; port:int=Field(5060,ge=1,le=65535); context:str='from-trunk'; transport:str='transport-udp'; codecs:list[str]=['ulaw']; identify_match:str=''; direct_media:bool=False; rtp_symmetric:bool=True; force_rport:bool=True; rewrite_contact:bool=True
    @field_validator('name','context','transport')
    @classmethod
    def names(cls,v):
        if not NAME.fullmatch(v): raise ValueError('Invalid name')
        return v
class ContextIn(BaseModel):
    name:str
class RouteIn(BaseModel):
    route_id:str|None=None; context:str; pattern:str='_X.'; destination:str|None=None; extension:str|None=None; caller_id:str=''; playback:str=''; timeout:int=Field(60,ge=1,le=600); description:str=''; record:bool=False
class SaveRequest(BaseModel):
    file:Literal['pjsip','extensions']; content:str; version:str; reload:bool=False
class ReloadRequest(BaseModel): target:Literal['pjsip','dialplan','all']
