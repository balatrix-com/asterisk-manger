const dialerForm=document.querySelector('#dialerForm');
if(dialerForm){
  const q=id=>document.getElementById(id);
  let hadTarget=false;
  let busy=false;
  function drawDialer(data){
    q('dialerState').textContent=data.state;
    q('dialerDetail').textContent=data.detail;
    q('dialerCurrentNumber').textContent=data.number||'—';
    q('dialerCurrentServer').textContent=data.server_ip?`${data.server_ip}:${data.server_port}`:'—';
    q('dialerAttempt').textContent=data.attempt||'—';
    q('dialerState').dataset.state=data.state.toLowerCase();
    q('dialerStart').disabled=busy||data.has_target;
    q('dialerStop').disabled=busy||!data.has_target;
    for(const id of ['dialerNumber','dialerIp','dialerPort'])q(id).disabled=data.has_target;
    if(data.has_target){
      q('dialerNumber').value=data.number||'';
      q('dialerIp').value=data.server_ip||'';
      q('dialerPort').value=data.server_port||5060;
    }else if(hadTarget){
      q('dialerNumber').value='';q('dialerIp').value='';q('dialerPort').value='5060';
    }
    hadTarget=data.has_target;
  }
  async function pollDialer(){
    if(busy)return;
    try{drawDialer(await api('/api/dialer/status'))}catch(error){q('dialerDetail').textContent=error.message}
  }
  dialerForm.addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;busy=true;q('dialerStart').disabled=true;
    try{
      const result=await api('/api/dialer/start',{method:'POST',body:JSON.stringify({
        number:q('dialerNumber').value.trim(),server_ip:q('dialerIp').value.trim(),server_port:Number(q('dialerPort').value)
      })});
      drawDialer(result);
    }catch(error){alert(error.message,true)}
    finally{busy=false;pollDialer()}
  });
  q('dialerStop').addEventListener('click',async()=>{
    if(busy)return;busy=true;q('dialerStop').disabled=true;
    try{drawDialer(await api('/api/dialer/stop',{method:'POST'}))}
    catch(error){alert(error.message,true)}
    finally{busy=false;pollDialer()}
  });
  pollDialer();setInterval(pollDialer,1000);
}
