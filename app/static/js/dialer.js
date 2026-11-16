const dialerForm=document.querySelector('#dialerForm');
if(dialerForm){
  const q=id=>document.getElementById(id);
  let hadTarget=false;
  let busy=false;
  function drawDialer(data){
    q('dialerState').textContent=data.state;
    q('dialerDetail').textContent=data.detail;
    q('dialerCurrentCallerId').textContent=data.caller_id||'—';
    q('dialerCurrentServer').textContent=data.server_ip?`${data.server_ip}:${data.server_port}`:'—';
    q('dialerCurrentMedia').textContent=data.media_mode==='music'?'Send test audio':data.media_mode==='echo'?'Echo received audio':'—';
    const rows=q('dialerCallRows');rows.replaceChildren();
    if(data.calls.length){
      for(const call of data.calls){
        const row=document.createElement('tr');
        for(const value of [call.number,call.state,String(call.attempt||'—'),call.detail]){
          const cell=document.createElement('td');cell.textContent=value;row.appendChild(cell);
        }
        rows.appendChild(row);
      }
    }else{
      const row=document.createElement('tr'),cell=document.createElement('td');
      cell.colSpan=4;cell.textContent='No test running.';row.appendChild(cell);rows.appendChild(row);
    }
    q('dialerState').dataset.state=data.state.toLowerCase();
    q('dialerStart').disabled=busy||data.has_target;
    q('dialerStop').disabled=busy||!data.has_target;
    for(const id of ['dialerNumbers','dialerCallerId','dialerIp','dialerPort','dialerMediaMode'])q(id).disabled=data.has_target;
    if(data.has_target){
      q('dialerNumbers').value=(data.numbers||[]).join('\n');
      q('dialerCallerId').value=data.caller_id||'';
      q('dialerIp').value=data.server_ip||'';
      q('dialerPort').value=data.server_port||5060;
      q('dialerMediaMode').value=data.media_mode||'echo';
    }else if(hadTarget){
      q('dialerNumbers').value='';q('dialerCallerId').value='';
      q('dialerIp').value='';q('dialerPort').value='5060';q('dialerMediaMode').value='echo';
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
        numbers:q('dialerNumbers').value.trim(),caller_id:q('dialerCallerId').value.trim(),
        server_ip:q('dialerIp').value.trim(),server_port:Number(q('dialerPort').value),
        media_mode:q('dialerMediaMode').value
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
