from types import SimpleNamespace
from unittest.mock import patch
import threading
import time

import pytest

from app.services.call_dialer import CallDialer,NumberState,Target


SETTINGS=SimpleNamespace(ami_host='127.0.0.1',ami_port=5038,ami_username='dialer',ami_secret='secret',dialer_endpoint='dialer-test')


def test_target_validation():
    valid={'numbers':'8000123951\n8000303030','caller_id':'1234567890',
           'server_ip':'91.99.251.58','server_port':5060}
    assert Target.parse(valid).numbers==('8000123951','8000303030')
    assert Target.parse({**valid,'media_mode':'music'}).media_mode=='music'
    for bad in ({**valid,'numbers':'1'},
                {**valid,'numbers':'8000123951\n8000123951'},
                {**valid,'caller_id':'1234'},
                {**valid,'server_ip':'invalid'},
                {**valid,'server_port':0},
                {**valid,'media_mode':'Playback'},
                {**valid,'media_mode':None},
                {**valid,'media_mode':['music']}):
        with pytest.raises(ValueError):Target.parse(bad)


class FakeAMI:
    instance=None
    def __init__(self,*_):
        self.sent=[];self.messages=[];self.closed=False;FakeAMI.instance=self
    def login(self,*_):pass
    def send(self,fields):
        self.sent.append(fields)
        if fields['Action']=='Originate':
            unique=fields['ChannelId'];action=fields['ActionID']
            self.messages=[
                {'Event':'Newchannel','Uniqueid':unique,'Channel':'PJSIP/dialer-test-0001'},
                {'Event':'Newstate','Uniqueid':unique,'ChannelStateDesc':'Up'},
                {'Event':'Hangup','Uniqueid':unique},
            ]
    def read(self,*_):return self.messages.pop(0) if self.messages else None
    def close(self):self.closed=True


def test_single_call_waits_for_hangup_and_clears_channel_id():
    dialer=CallDialer(SETTINGS)
    target=Target(('8000123951',),'1234567890','91.99.251.58',5060)
    dialer.calls={'8000123951':NumberState()}
    states=[]
    original_set=dialer._set
    def capture(number,state,detail):
        states.append(state)
        original_set(number,state,detail)
    dialer._set=capture
    with patch('app.services.call_dialer.AMIClient',FakeAMI):dialer._one_call('8000123951',target)
    sent=FakeAMI.instance.sent[0]
    assert sent['Channel']=='PJSIP/dialer-test/sip:8000123951@91.99.251.58:5060'
    assert sent['Application']=='Echo'
    assert sent['CallerID']=='Call Test <1234567890>'
    assert dialer.calls['8000123951'].active_uniqueid is None
    assert dialer.calls['8000123951'].state=='Disconnected'
    assert states==['Connected','Disconnected']
    assert FakeAMI.instance.closed


def test_music_mode_sends_continuous_audio_application():
    dialer=CallDialer(SETTINGS)
    target=Target(('8000123951',),'1234567890','91.99.251.58',5060,'music')
    dialer.calls={'8000123951':NumberState()}
    with patch('app.services.call_dialer.AMIClient',FakeAMI):dialer._one_call('8000123951',target)
    sent=FakeAMI.instance.sent[0]
    assert sent['Application']=='MusicOnHold'
    assert sent['Data']=='default'
    assert dialer.snapshot()['calls'][0]['state']=='Disconnected'


def test_start_refuses_existing_target_even_after_worker_stopped():
    dialer=CallDialer(SETTINGS)
    dialer.target=Target(('8000123951',),'1234567890','91.99.251.58',5060)
    with pytest.raises(RuntimeError):dialer.start(Target(('8000303030',),'1234567890','91.99.251.58',5060))


def test_stop_hangs_up_only_the_test_channel():
    dialer=CallDialer(SETTINGS)
    target=Target(('8000123951',),'1234567890','91.99.251.58',5060)
    dialer.calls={'8000123951':NumberState()}

    class StoppingAMI(FakeAMI):
        def send(self,fields):
            super().send(fields)
            if fields['Action']=='Hangup':
                self.messages.append({'Event':'Hangup','Uniqueid':self.sent[0]['ChannelId']})
        def read(self,*args):
            message=super().read(*args)
            if message and message.get('Event')=='Newchannel':
                dialer.stop_event.set()
                self.messages=[]
            return message

    with patch('app.services.call_dialer.AMIClient',StoppingAMI):dialer._one_call('8000123951',target)
    assert FakeAMI.instance.sent[1]=={'Action':'Hangup','Channel':'PJSIP/dialer-test-0001'}
    assert dialer.calls['8000123951'].active_uniqueid is None


def test_recovery_finds_exact_channel_before_hangup():
    dialer=CallDialer(SETTINGS)
    dialer.calls={'8000123951':NumberState(active_uniqueid='dialer-test-id')}

    class RecoveryAMI(FakeAMI):
        def send(self,fields):
            self.sent.append(fields)
            if fields['Action']=='Status':
                self.messages=[
                    {'Event':'Status','Uniqueid':'unrelated','Channel':'PJSIP/other-0001'},
                    {'Event':'Status','Uniqueid':'dialer-test-id','Channel':'PJSIP/dialer-test-0002'},
                    {'Event':'StatusComplete'},
                ]
            elif fields['Action']=='Hangup':
                self.messages=[{'Event':'Hangup','Uniqueid':'dialer-test-id'}]

    with patch('app.services.call_dialer.AMIClient',RecoveryAMI):dialer._recover_hangup('8000123951','dialer-test-id')
    assert FakeAMI.instance.sent[1]=={'Action':'Hangup','Channel':'PJSIP/dialer-test-0002'}
    assert dialer.calls['8000123951'].active_uniqueid is None


def test_each_number_redials_only_after_its_own_call_ends():
    dialer=CallDialer(SETTINGS,retry_seconds=0.01)
    first_finished=threading.Event()
    guard=threading.Lock()
    active={number:0 for number in ('8000123951','8000303030')}
    maximum=active.copy()
    started=active.copy()

    def fake_call(number,_target):
        with guard:
            active[number]+=1
            started[number]+=1
            maximum[number]=max(maximum[number],active[number])
            sequence=started[number]
        if number=='8000123951' and sequence==1:
            first_finished.wait(2)
        else:
            dialer.stop_event.wait(2)
        with guard:active[number]-=1

    dialer._one_call=fake_call
    target=Target(('8000123951','8000303030'),'1234567890','91.99.251.58',5060)
    dialer.start(target)
    try:
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            with guard:
                if started['8000123951']==1 and started['8000303030']==1:break
            time.sleep(0.01)
        first_finished.set()
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            with guard:
                if started['8000123951']>=2:break
            time.sleep(0.01)
        with guard:
            assert started['8000123951']>=2
            assert started['8000303030']==1
            assert maximum=={'8000123951':1,'8000303030':1}
    finally:
        first_finished.set()
        dialer.stop()
    assert dialer.snapshot()['calls']==[]
    assert dialer.snapshot()['caller_id'] is None
