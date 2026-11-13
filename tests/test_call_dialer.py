from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.call_dialer import CallDialer,Target


SETTINGS=SimpleNamespace(ami_host='127.0.0.1',ami_port=5038,ami_username='dialer',ami_secret='secret',dialer_endpoint='dialer-test')


def test_target_validation():
    assert Target.parse({'number':'8000123951','server_ip':'91.99.251.58','server_port':5060}).server_port==5060
    for bad in ({'number':'1','server_ip':'91.99.251.58','server_port':5060},
                {'number':'8000123951','server_ip':'invalid','server_port':5060},
                {'number':'8000123951','server_ip':'91.99.251.58','server_port':0}):
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
    target=Target('8000123951','91.99.251.58',5060)
    states=[]
    original_set=dialer._set
    def capture(state,detail):
        states.append(state)
        original_set(state,detail)
    dialer._set=capture
    with patch('app.services.call_dialer.AMIClient',FakeAMI):dialer._one_call(target)
    sent=FakeAMI.instance.sent[0]
    assert sent['Channel']=='PJSIP/dialer-test/sip:8000123951@91.99.251.58:5060'
    assert sent['Application']=='Echo'
    assert dialer.active_uniqueid is None
    assert dialer.state=='Disconnected'
    assert states==['Connected','Disconnected']
    assert FakeAMI.instance.closed


def test_start_refuses_existing_target_even_after_worker_stopped():
    dialer=CallDialer(SETTINGS)
    dialer.target=Target('8000123951','91.99.251.58',5060)
    with pytest.raises(RuntimeError):dialer.start(Target('8000303030','91.99.251.58',5060))


def test_stop_hangs_up_only_the_test_channel():
    dialer=CallDialer(SETTINGS)
    target=Target('8000123951','91.99.251.58',5060)

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

    with patch('app.services.call_dialer.AMIClient',StoppingAMI):dialer._one_call(target)
    assert FakeAMI.instance.sent[1]=={'Action':'Hangup','Channel':'PJSIP/dialer-test-0001'}
    assert dialer.active_uniqueid is None


def test_recovery_finds_exact_channel_before_hangup():
    dialer=CallDialer(SETTINGS)
    dialer.active_uniqueid='dialer-test-id'

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

    with patch('app.services.call_dialer.AMIClient',RecoveryAMI):dialer._recover_hangup('dialer-test-id')
    assert FakeAMI.instance.sent[1]=={'Action':'Hangup','Channel':'PJSIP/dialer-test-0002'}
    assert dialer.active_uniqueid is None
