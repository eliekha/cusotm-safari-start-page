// BriefDesk - Hub Module
// Meeting prep, prefetch status, data sources UI

// ============================================================================
// Hub Functions
// ============================================================================
var hubExpanded={prep:true};
var hubCache={prep:null};

function toggleHubSection(section){
var el=document.getElementById('hub-'+section);
if(el){
el.classList.toggle('collapsed');
hubExpanded[section]=!el.classList.contains('collapsed');
// Also toggle container minimized state
var container=el.closest('.hub-container,.hub-prep-container');
if(container){
container.classList.toggle('minimized',el.classList.contains('collapsed'));
}
}
}

function relativeTime(isoString){
if(!isoString)return '';
var date=new Date(isoString);
var now=new Date();
var diff=Math.floor((now-date)/1000);
if(diff<60)return 'just now';
if(diff<3600)return Math.floor(diff/60)+'m ago';
if(diff<86400)return Math.floor(diff/3600)+'h ago';
if(diff<604800)return Math.floor(diff/86400)+'d ago';
return date.toLocaleDateString('en-US',{month:'short',day:'numeric'});
}

// Generate consistent color from name
function nameToColor(name){
var colors=['#e91e63','#9c27b0','#673ab7','#3f51b5','#2196f3','#03a9f4','#00bcd4','#009688','#4caf50','#8bc34a','#ff9800','#ff5722','#795548','#607d8b'];
var hash=0;
for(var i=0;i<name.length;i++)hash=name.charCodeAt(i)+((hash<<5)-hash);
return colors[Math.abs(hash)%colors.length];
}

// Get initials from name
function getInitials(name){
if(!name)return '?';
var parts=name.trim().split(/\s+/);
if(parts.length>=2)return(parts[0][0]+parts[parts.length-1][0]).toUpperCase();
return name.substring(0,2).toUpperCase();
}

function renderHubItem(item,type){
var iconClass='';
var icon='';
var title=item.name||item.title||item.subject||item.text||'Untitled';
var meta='';
var link='';
var time=item.time||item.timestamp?relativeTime(item.time||item.timestamp):'';
var actions='';
var useAvatar=false;
var avatarInitials='';
var avatarColor='';

if(type==='slack'){
// Slack message rendering - simplified for meeting prep context
var channel=item.channel||'';
var isDM=channel.startsWith('DM with')||channel==='DM'||channel==='Group DM';
meta=item.from||item.user||channel||'';

// Build Slack link
link=item.slack_url||item.url||item.link||'';
if(!link){
var chId=item.channel_id||item.channelId||'';
var msgTs=item.msg_id||item.msgid||item.thread_ts||item.ts||'';
if(chId&&msgTs){
var cleanTs=String(msgTs).replace('.','');
var slackDomain=window.SLACK_WORKSPACE||'your-workspace';
link='https://'+slackDomain+'.slack.com/archives/'+chId+'/p'+cleanTs;
}else if(chId){
var slackDomain=window.SLACK_WORKSPACE||'your-workspace';
link='https://'+slackDomain+'.slack.com/archives/'+chId;
}
}

if(isDM&&item.from){
useAvatar=true;
avatarInitials=getInitials(item.from);
avatarColor=nameToColor(item.from);
iconClass='avatar';
}else{
iconClass='slack';
icon='<img src="icons/slack.png" alt="Slack">';
}

if(link){
actions='<div class="hub-item-actions">';
actions+='<a href="'+link+'" class="hub-action-btn open" target="_blank" title="Open in Slack"><svg viewBox="0 0 24 24"><path d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg></a>';
actions+='</div>';
}
}else if(type==='jira'){
iconClass='jira';
icon='<img src="icons/jira.svg" alt="Jira">';
meta=item.key||item.status||'';
link=item.url||'';
}else if(type==='confluence'){
iconClass='confluence';
icon='<img src="icons/confluence.svg" alt="Confluence">';
meta=item.space||'';
link=item.url||'';
}else if(type==='drive'){
iconClass='drive';
icon='<img src="icons/drive.png" alt="Google Drive">';
meta=item.type||item.drive||'';
// Use Drive URL if available (API mode), otherwise local file path (fallback mode)
if(item.url){
link=item.url;
}else if(item.webViewLink){
link=item.webViewLink;
}else if(item.id&&item.id.length>10){
// Construct Drive URL from file ID if available
link='https://drive.google.com/file/d/'+item.id+'/view';
}else if(item.full_path){
link='file://'+item.full_path;
}else{
link='';
}
}else if(type==='gmail'){
iconClass='gmail';
icon='<img src="icons/gmail.png" alt="Gmail">';
// Show sender and date
var sender=item.from||'';
if(sender.includes('<'))sender=sender.split('<')[0].trim();
meta=sender+(item.date?' · '+item.date:'');
// Build Gmail URL if not provided
link=item.url||'';
if(!link&&item.id){
link='https://mail.google.com/mail/u/0/#inbox/'+item.id;
}else if(!link){
link='https://mail.google.com/mail/u/0/#inbox';
}
}

// For Slack conversations, make entire row clickable
var rowClick='';
if(type==='slack'&&item.type==='conversation'){
var convType=item.conv_type||'dm';
var channelId=item.channel_id||'';
if(convType==='thread'){
rowClick=' onclick="openThreadsPanel()" style="cursor:pointer"';
}else if(convType==='channel'){
var chatData=JSON.stringify({channel_id:channelId,name:item.name||'Channel',type:'channel'}).replace(/"/g,'&quot;');
rowClick=' onclick="openChatPanel('+chatData+')" style="cursor:pointer"';
}else{
// DM or group_dm
var chatChannelId=convType==='dm'?'@'+(item.username||item.name):channelId;
var chatData=JSON.stringify({channel_id:chatChannelId,name:item.name||'Chat',type:convType}).replace(/"/g,'&quot;');
rowClick=' onclick="openChatPanel('+chatData+')" style="cursor:pointer"';
}
}

var html='<div class="hub-item '+(useAvatar?'':iconClass)+'"'+rowClick+'>';
if(useAvatar){
html+='<div class="hub-item-icon avatar" style="background:'+avatarColor+'">'+avatarInitials+'</div>';
}else{
html+='<div class="hub-item-icon '+iconClass+'">'+icon+'</div>';
}
html+='<div class="hub-item-body">';
// Make clickable if there's a link and either not slack OR slack without action buttons
if(link&&(type!=='slack'||!actions)){
html+='<a href="'+link+'" class="hub-item-link" target="_blank"><div class="hub-item-title">'+escapeHtml(title)+'</div></a>';
}else{
html+='<div class="hub-item-title">'+escapeHtml(title)+'</div>';
}
html+='<div class="hub-item-row">';
if(meta)html+='<div class="hub-item-meta">'+escapeHtml(meta)+'</div>';
if(time)html+='<div class="hub-item-time">'+time+'</div>';
html+='</div>';
html+='</div>';
html+=actions;
html+='</div>';
return html;
}

function escapeHtml(str){
if(!str)return '';
return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatSummary(text){
if(!text)return '';
// Simple markdown to HTML conversion for the summary
var html=escapeHtml(text);
// Convert headers
html=html.replace(/^## (.+)$/gm,'<h3 class="summary-h2">$1</h3>');
html=html.replace(/^### (.+)$/gm,'<h4 class="summary-h3">$1</h4>');
// Convert bullet points
html=html.replace(/^- (.+)$/gm,'<li>$1</li>');
// Wrap consecutive li elements in ul
html=html.replace(/(<li>.*<\/li>\n?)+/g,'<ul>$&</ul>');
// Convert bold
html=html.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
// Convert newlines to br
html=html.replace(/\n\n/g,'</p><p>');
html=html.replace(/\n/g,'<br>');
return '<div class="summary-text"><p>'+html+'</p></div>';
}

function renderMeetingPrep(data){
var container=document.getElementById('hub-prep');
var content=document.getElementById('hub-prep-content');
var badge=document.getElementById('hub-prep-badge');
var subtitle=document.getElementById('hub-prep-subtitle');

if(!data||!data.meeting){
container.style.display='none';
return;
}

container.style.display='block';
var meeting=data.meeting;
var mins=meeting.minutes_until||0;
var countdownClass='hub-prep-meeting-countdown';
var countdownText='';
if(mins<=0){countdownText='Starting now';countdownClass+=' now';}
else if(mins<=15){countdownText='In '+mins+' min';countdownClass+=' soon';}
else if(mins<60){countdownText='In '+mins+' min';}
else{var hrs=Math.floor(mins/60);var m=mins%60;countdownText='In '+hrs+'h'+(m>0?' '+m+'m':'');}

subtitle.textContent=meeting.title;

var html='<div class="hub-prep-meeting">';
html+='<div class="hub-prep-meeting-header">';
html+='<div class="hub-prep-meeting-info">';
html+='<div class="hub-prep-meeting-title">'+escapeHtml(meeting.title)+'</div>';
html+='<div class="hub-prep-meeting-details">';
html+='<div class="hub-prep-meeting-time"><svg viewBox="0 0 24 24"><path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"/></svg>'+escapeHtml(meeting.start_formatted||'')+'</div>';
html+='<div class="'+countdownClass+'">'+countdownText+'</div>';
html+='</div></div>';
if(meeting.meet_link){
html+='<a href="'+meeting.meet_link+'" class="cal-join" target="_blank"><svg viewBox="0 0 24 24"><path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/></svg>Join</a>';
}
html+='</div></div>';

var totalItems=0;

// Jira context
if(data.jira&&Array.isArray(data.jira)&&data.jira.length>0){
html+='<div class="hub-prep-section"><div class="hub-prep-section-title">Related Jira</div><div class="hub-items">';
data.jira.forEach(function(item){html+=renderHubItem(item,'jira');});
html+='</div></div>';
totalItems+=data.jira.length;
}

// Confluence context
if(data.confluence&&Array.isArray(data.confluence)&&data.confluence.length>0){
html+='<div class="hub-prep-section"><div class="hub-prep-section-title">Related Docs</div><div class="hub-items">';
data.confluence.forEach(function(item){html+=renderHubItem(item,'confluence');});
html+='</div></div>';
totalItems+=data.confluence.length;
}

// Google Drive context
if(data.google_drive&&Array.isArray(data.google_drive)&&data.google_drive.length>0){
html+='<div class="hub-prep-section"><div class="hub-prep-section-title">Related Files</div><div class="hub-items">';
data.google_drive.forEach(function(item){html+=renderHubItem(item,'drive');});
html+='</div></div>';
totalItems+=data.google_drive.length;
}

// AI Insights summary
if(data.insights){
html+='<div class="hub-insights"><div class="hub-insights-icon"><svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg></div><div class="hub-insights-text">'+escapeHtml(data.insights)+'</div></div>';
}

if(totalItems===0&&!data.insights){
html+='<div class="hub-empty"><div class="hub-empty-icon"><svg viewBox="0 0 24 24"><path d="M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-1 12H5c-.55 0-1-.45-1-1V9c0-.55.45-1 1-1h14c.55 0 1 .45 1 1v8c0 .55-.45 1-1 1z"/></svg></div><div class="hub-empty-text">No related context found</div><div class="hub-empty-hint">Context appears based on meeting title keywords</div></div>';
}

badge.textContent=totalItems>0?totalItems:'';
content.innerHTML=html;
}

// Meeting prep state for progressive loading
var prepState={meeting:null,jira:[],confluence:[],google_drive:[],slack:[],gmail:[],summary:null,loading:{jira:true,confluence:true,drive:true,slack:true,gmail:true,summary:true}};
// Meeting navigation state
var allMeetings=[];
var currentMeetingIndex=0;
// Week view state
var weekData=[];
var selectedDate=null;

function updateMeetingNav(){
var nav=document.getElementById('meeting-nav');
var indicator=document.getElementById('meeting-nav-indicator');
var prevBtn=document.getElementById('meeting-prev');
var nextBtn=document.getElementById('meeting-next');
if(allMeetings.length>1){
nav.classList.add('show');
indicator.textContent=(currentMeetingIndex+1)+'/'+allMeetings.length;
prevBtn.disabled=currentMeetingIndex===0;
nextBtn.disabled=currentMeetingIndex>=allMeetings.length-1;
}else{
nav.classList.remove('show');
}
}

var _navigateDebounceTimer=null;
function navigateMeeting(direction){
var newIndex=currentMeetingIndex+direction;
if(newIndex<0||newIndex>=allMeetings.length)return;
currentMeetingIndex=newIndex;
updateMeetingNav();
// Debounce: wait 200ms after last click before fetching
if(_navigateDebounceTimer)clearTimeout(_navigateDebounceTimer);
_navigateDebounceTimer=setTimeout(function(){
_navigateDebounceTimer=null;
fetchMeetingPrepForIndex(currentMeetingIndex);
},200);
}

function toggleAggressivePrefetch(currentlyForced){
if(!currentlyForced){
// Turning ON force mode - require confirmation
if(!confirm('Force mode will refresh ALL meetings regardless of cache.\n\nThis may take a while and use more resources.\n\nContinue?')){
return;
}
}
fetch(S+'/hub/prefetch/control?action=force')
.then(function(r){return r.json();})
.then(function(d){
console.log('Prefetch mode:',d.message);
fetchPrefetchStatus(); // Refresh status display
})
.catch(function(e){console.error('Toggle error:',e);});
}

function fetchServiceHealth(){
var container=document.getElementById('service-health-container');
if(!container)return;
container.innerHTML='<div style="text-align:center;padding:12px;color:rgba(255,255,255,.4)"><svg width="16" height="16" viewBox="0 0 24 24" style="animation:spin 1s linear infinite"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="32" stroke-linecap="round"/></svg></div>';
fetch(S+'/hub/service-health')
.then(function(r){return r.json();})
.then(function(data){
var html='';
var hasFailedMCP=false;
data.services.forEach(function(svc){
var isOk=svc.status==='ok';
var statusColor=isOk?'#4ade80':'#f87171';
var statusIcon=isOk?'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>':'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>';
html+='<div style="display:flex;align-items:center;gap:12px;padding:10px 12px;background:rgba(255,255,255,.04);border-radius:8px;border-left:3px solid '+statusColor+'">';
html+='<div style="color:'+statusColor+'">'+statusIcon+'</div>';
html+='<div style="flex:1">';
html+='<div style="font-size:13px;color:rgba(255,255,255,.9)">'+svc.name+' <span style="color:rgba(255,255,255,.3);font-size:11px">:'+svc.port+'</span></div>';
html+='<div style="font-size:11px;color:rgba(255,255,255,.4)">'+svc.description+'</div>';
if(svc.mcp){
var connectedServers=svc.mcp.servers.filter(function(s){return s.status==='connected';});
var errorServers=svc.mcp.servers.filter(function(s){return s.status==='error';});
if(connectedServers.length>0){
var mcpNames=connectedServers.map(function(s){return s.name+'('+s.tools+')'}).join(', ');
html+='<div style="font-size:10px;color:#60a5fa;margin-top:2px">MCP: '+connectedServers.length+' connected - '+mcpNames+'</div>';
}
if(errorServers.length>0){
hasFailedMCP=true;
errorServers.forEach(function(es){
var errorMsg=(es.error||'Connection error').substring(0,60);
var reAuthLink='';
// Add re-auth links for known MCPs
if(es.name==='atlassian'){
reAuthLink=' <a href="#" onclick="showAtlassianReauth();return false;" style="color:#60a5fa;text-decoration:underline">Re-authenticate</a>';
}else if(es.name==='gmail'){
reAuthLink=' <a href="#" onclick="showGmailReauth();return false;" style="color:#60a5fa;text-decoration:underline">Re-authenticate</a>';
}else if(es.name==='slack'){
reAuthLink=' <a href="#" onclick="showSlackReauth();return false;" style="color:#60a5fa;text-decoration:underline">Re-authenticate</a>';
}
html+='<div style="font-size:10px;color:#f87171;margin-top:2px">✗ '+es.name+': '+errorMsg+reAuthLink+'</div>';
});
}
}
// Show GDrive MCP status
if(svc.gdriveMcp){
var driveAvailable=svc.gdriveMcp.available;
var driveColor=driveAvailable?'#4ade80':'#f59e0b';
var driveIcon=driveAvailable?'✓':'⚠';
var driveMode=driveAvailable?'API Mode (full-text search)':'Local Fallback (filename only)';
html+='<div style="font-size:10px;color:'+driveColor+';margin-top:2px">'+driveIcon+' Google Drive: '+driveMode+'</div>';
}
if(svc.error){
html+='<div style="font-size:10px;color:#f87171;margin-top:2px">'+svc.error+'</div>';
}
html+='</div>';
html+='<div style="font-size:11px;color:'+statusColor+';font-weight:500">'+(isOk?'OK':'Error')+'</div>';
html+='</div>';
});
// Add retry/restart buttons if there are failed MCP servers
if(hasFailedMCP){
html+='<div style="margin-top:8px;padding:10px 12px;background:rgba(248,113,113,.1);border-radius:8px">';
html+='<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">';
html+='<div style="font-size:12px;color:#f87171">Some MCP servers failed to connect</div>';
html+='<button id="mcp-retry-btn" onclick="retryFailedMCP()" style="padding:6px 12px;background:#f87171;border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:11px;font-weight:500">Retry</button>';
html+='</div>';
html+='<div style="display:flex;align-items:center;justify-content:space-between">';
html+='<div style="font-size:11px;color:rgba(255,255,255,.5)">After re-auth, restart to apply new credentials:</div>';
html+='<button onclick="restartSearchService()" style="padding:6px 12px;background:#3b82f6;border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:11px;font-weight:500">Restart Service</button>';
html+='</div>';
html+='</div>';
}
container.innerHTML=html;
})
.catch(function(e){
container.innerHTML='<div style="font-size:12px;color:#f87171;text-align:center;padding:12px">Failed to load service health</div>';
});
}

function retryFailedMCP(){
var btn=document.getElementById('mcp-retry-btn');
if(btn){
btn.disabled=true;
btn.innerHTML='<span style="display:inline-flex;align-items:center;gap:6px"><svg width="12" height="12" viewBox="0 0 24 24" style="animation:spin 1s linear infinite"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="32" stroke-linecap="round"/></svg>Retrying...</span>';
}
fetch('http://127.0.0.1:19765/retry',{method:'POST'})
.then(function(r){return r.json();})
.then(function(data){
console.log('MCP retry result:',data);
// Refresh service health to show updated status
setTimeout(fetchServiceHealth,500);
})
.catch(function(e){
console.error('MCP retry error:',e);
if(btn){
btn.disabled=false;
btn.textContent='Retry Failed';
}
});
}

// Re-authentication helper functions for failed MCPs
function showAtlassianReauth(){
if(confirm('Re-authenticate Atlassian?\n\nThis will open your browser to sign in.')){
triggerMcpReauth('atlassian');
}
}

function showGmailReauth(){
if(confirm('Re-authenticate Gmail?\n\nThis will open your browser to sign in with Google.')){
triggerMcpReauth('gmail');
}
}

function showDriveReauth(){
if(confirm('Re-authenticate Google Drive?\n\nThis will open your browser to sign in with Google.')){
triggerMcpReauth('drive');
}
}

function showSlackReauth(){
alert('Slack tokens have expired.\n\nTo re-authenticate:\n1. Open app.slack.com in your browser\n2. Open DevTools (Cmd+Option+I)\n3. Go to Application → Cookies → copy the "d" cookie (XOXD)\n4. In Console, run the snippet to get XOXC token\n5. Update tokens in Settings or .devsai.json');
}

function triggerMcpReauth(mcp){
fetch(S+'/hub/mcp-reauth?mcp='+mcp)
.then(function(r){return r.json();})
.then(function(data){
if(data.success){
alert(data.message+'\n\nAfter signing in, click "Restart Search Service" to apply new credentials.');
}else{
alert('Error: '+(data.error||'Unknown error'));
}
})
.catch(function(e){
alert('Failed to start re-authentication: '+e.message);
});
}

function restartSearchService(){
if(!confirm('Restart the search service to apply new credentials?'))return;
fetch(S+'/hub/restart-search-service',{method:'POST'})
.then(function(r){return r.json();})
.then(function(data){
if(data.success){
alert('Search service restarting... Please wait a few seconds then refresh.');
setTimeout(fetchServiceHealth,3000);
}else{
alert('Error: '+(data.error||'Unknown error'));
}
})
.catch(function(e){
alert('Failed to restart: '+e.message);
});
}

function fetchPrefetchStatus(){
var refreshBtn=document.getElementById('status-refresh-btn');
var currentEl=document.getElementById('prefetch-status-current');
// Show loading state
if(refreshBtn){
refreshBtn.disabled=true;
refreshBtn.innerHTML='<span style="display:inline-flex;align-items:center;gap:6px"><svg width="12" height="12" viewBox="0 0 24 24" style="animation:spin 1s linear infinite"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="32" stroke-linecap="round"/></svg>Loading...</span>';
}
currentEl.innerHTML='<div style="text-align:center;padding:16px;color:rgba(255,255,255,.5)"><svg width="20" height="20" viewBox="0 0 24 24" style="animation:spin 1s linear infinite"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="32" stroke-linecap="round"/></svg></div>';
// Synthetic delay for better UX feedback
setTimeout(function(){
fetch(S+'/hub/prefetch-status')
.then(function(r){return r.json();})
.then(function(data){
var logEl=document.getElementById('prefetch-activity-log');
// Update current status
var statusHtml='<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">';
statusHtml+='<div><span style="color:rgba(255,255,255,.5)">Status:</span> <span style="color:'+(data.running?'#4ade80':'rgba(255,255,255,.7)')+'">'+( data.running?'Running':'Idle')+'</span></div>';
statusHtml+='<div><span style="color:rgba(255,255,255,.5)">Meetings:</span> <span style="color:rgba(255,255,255,.7)">'+data.meetings_processed+'/'+data.meetings_in_queue+'</span></div>';
var modeColor=data.mode==='aggressive'?'#4ade80':'#fbbf24';
statusHtml+='<div><span style="color:rgba(255,255,255,.5)">Mode:</span> <span style="color:'+modeColor+'">'+data.mode+'</span> <span style="color:rgba(255,255,255,.3);font-size:10px">('+data.mode_reason+')</span></div>';
statusHtml+='<div><button onclick="toggleAggressivePrefetch('+data.force_aggressive+')" style="font-size:10px;padding:2px 8px;background:'+(data.force_aggressive?'#4ade80':'rgba(255,255,255,.1)')+';border:none;border-radius:4px;color:'+(data.force_aggressive?'#000':'rgba(255,255,255,.7)')+';cursor:pointer">'+(data.force_aggressive?'Force ON':'Force Refresh')+'</button></div>';
if(data.day_mode_note){
statusHtml+='<div style="grid-column:1/-1;color:#fbbf24;font-size:10px;padding:4px 0">⚠ '+data.day_mode_note+'</div>';
}
if(data.current_meeting){
statusHtml+='<div style="grid-column:1/-1"><span style="color:rgba(255,255,255,.5)">Meeting:</span> <span style="color:#60a5fa">'+data.current_meeting+'</span></div>';
}
if(data.current_source){
statusHtml+='<div style="grid-column:1/-1"><span style="color:rgba(255,255,255,.5)">Source:</span> <span style="color:#fbbf24">'+data.current_source+'</span></div>';
}
statusHtml+='</div>';
currentEl.innerHTML=statusHtml;
// Update activity log
if(data.activity_log&&data.activity_log.length>0){
var logHtml='';
data.activity_log.forEach(function(entry){
var time=new Date(entry.timestamp*1000).toLocaleTimeString();
var statusColor=entry.status==='success'?'#4ade80':entry.status==='error'?'#f87171':entry.status==='warning'?'#fbbf24':'rgba(255,255,255,.5)';
var icon=entry.status==='success'?'✓':entry.status==='error'?'✗':entry.status==='warning'?'⚠':'•';
logHtml+='<div style="padding:6px 8px;border-bottom:1px solid rgba(255,255,255,.05);font-size:11px">';
logHtml+='<div style="display:flex;gap:8px;align-items:flex-start">';
logHtml+='<span style="color:'+statusColor+';min-width:12px">'+icon+'</span>';
logHtml+='<span style="color:rgba(255,255,255,.4);min-width:65px">'+time+'</span>';
logHtml+='<div style="flex:1">';
logHtml+='<span style="color:rgba(255,255,255,.8)">'+entry.message+'</span>';
if(entry.meeting)logHtml+='<div style="color:rgba(255,255,255,.4);font-size:10px;margin-top:2px">'+entry.meeting+'</div>';
logHtml+='</div>';
if(entry.source)logHtml+='<span style="color:#60a5fa;font-size:10px">'+entry.source+'</span>';
logHtml+='</div></div>';
});
logEl.innerHTML=logHtml;
}else{
logEl.innerHTML='<div style="font-size:12px;color:rgba(255,255,255,.4);text-align:center;padding:20px">No activity yet</div>';
}
// Reset button
if(refreshBtn){refreshBtn.disabled=false;refreshBtn.textContent='Refresh';}
})
.catch(function(e){
console.error('Prefetch status error:',e);
currentEl.innerHTML='<div style="color:#f87171;font-size:12px">Error: '+(e.message||'Failed to fetch')+'</div>';
if(refreshBtn){refreshBtn.disabled=false;refreshBtn.textContent='Refresh';}
});
},400);
}

var _promptsData={};
function loadPrompts(){
var container=document.getElementById('prompts-container');
container.innerHTML='<div style="font-size:12px;color:rgba(255,255,255,.5);text-align:center;padding:20px">Loading...</div>';
fetch(S+'/hub/prompts')
.then(function(r){return r.json();})
.then(function(data){
_promptsData=data.prompts||{};
var html='';
var sourceNames={jira:'Jira',confluence:'Confluence',slack:'Slack',gmail:'Gmail',drive:'Google Drive',summary:'AI Summary'};
Object.keys(_promptsData).forEach(function(source){
var p=_promptsData[source];
var name=sourceNames[source]||source;
var isCustom=p.is_custom;
html+='<div class="prompt-item" style="background:rgba(255,255,255,.04);border-radius:8px;padding:12px">';
html+='<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">';
html+='<span style="font-size:13px;color:rgba(255,255,255,.9)">'+name+'</span>';
html+='<div style="display:flex;gap:8px;align-items:center">';
if(isCustom)html+='<span style="font-size:10px;color:#4ade80;background:rgba(74,222,128,.15);padding:2px 6px;border-radius:4px">Custom</span>';
html+='<button onclick="resetPrompt(\''+source+'\')" style="font-size:10px;padding:4px 8px;background:rgba(255,255,255,.1);border:none;border-radius:4px;color:rgba(255,255,255,.6);cursor:pointer">Reset</button>';
html+='</div></div>';
html+='<textarea id="prompt-'+source+'" style="width:100%;min-height:120px;background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.1);border-radius:6px;padding:10px;color:rgba(255,255,255,.8);font-size:11px;font-family:monospace;resize:vertical;box-sizing:border-box" oninput="markPromptChanged(\''+source+'\')">'+escapeHtml(p.current)+'</textarea>';
html+='<button id="save-prompt-'+source+'" onclick="savePrompt(\''+source+'\')" style="display:none;margin-top:8px;padding:6px 12px;background:#6366f1;border:none;border-radius:6px;color:#fff;font-size:11px;cursor:pointer">Save Changes</button>';
html+='</div>';
});
container.innerHTML=html;
})
.catch(function(e){
container.innerHTML='<div style="color:#f87171;font-size:12px">Error: '+e.message+'</div>';
});
}

function escapeHtml(str){
return String(str||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function markPromptChanged(source){
document.getElementById('save-prompt-'+source).style.display='inline-block';
}

function savePrompt(source){
var textarea=document.getElementById('prompt-'+source);
var prompt=textarea.value;
var btn=document.getElementById('save-prompt-'+source);
btn.textContent='Saving...';
btn.disabled=true;
fetch(S+'/hub/prompts',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({source:source,prompt:prompt})
})
.then(function(r){return r.json();})
.then(function(data){
if(data.error){
alert('Error: '+data.error);
btn.textContent='Save Changes';
btn.disabled=false;
}else{
btn.style.display='none';
btn.textContent='Save Changes';
btn.disabled=false;
loadPrompts(); // Reload to show updated state
}
})
.catch(function(e){
alert('Error saving: '+e.message);
btn.textContent='Save Changes';
btn.disabled=false;
});
}

function resetPrompt(source){
if(!confirm('Reset '+source+' prompt to default?'))return;
fetch(S+'/hub/prompts',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({source:source,prompt:''})
})
.then(function(r){return r.json();})
.then(function(){loadPrompts();})
.catch(function(e){alert('Error: '+e.message);});
}

function fetchWeekData(){
fetch(S+'/hub/prep/week',{signal:AbortSignal.timeout(10000)})
.then(function(r){return r.json();})
.then(function(data){
if(data.error||!data.days)return;
weekData=data.days;
renderDayTabs();
// Auto-select today or first day with meetings
var dayToSelect=weekData.find(function(d){return d.meeting_count>0;})||weekData[0];
if(dayToSelect)selectDay(dayToSelect.date);
})
.catch(function(e){console.log('Week fetch error:',e);});
}

function renderDayTabs(){
var container=document.getElementById('day-tabs');
if(!weekData.length){container.style.display='none';return;}
container.style.display='flex';
var html='';
weekData.forEach(function(day){
var activeClass=day.date===selectedDate?' active':'';
var hasMeetings=day.meeting_count>0?' has-meetings':'';
html+='<button class="day-tab'+activeClass+hasMeetings+'" onclick="selectDay(\''+day.date+'\')">';
html+='<span class="day-tab-name">'+day.day_name+'</span>';
html+='<span class="day-tab-date">'+day.day_short+'</span>';
if(day.meeting_count>0)html+='<span class="day-count">'+day.meeting_count+'</span>';
html+='</button>';
});
container.innerHTML=html;
}

var _selectDayDebounceTimer=null;
function selectDay(date){
selectedDate=date;
currentMeetingIndex=0;
renderDayTabs();
// Debounce: wait 150ms after last click before fetching
if(_selectDayDebounceTimer)clearTimeout(_selectDayDebounceTimer);
_selectDayDebounceTimer=setTimeout(function(){
_selectDayDebounceTimer=null;
fetchMeetingPrepForIndex(0);
},150);
}

function renderMeetingPrepProgressive(){
var container=document.getElementById('hub-prep');
var content=document.getElementById('hub-prep-content');
var badge=document.getElementById('hub-prep-badge');
var subtitle=document.getElementById('hub-prep-subtitle');

if(!prepState.meeting){
container.style.display='none';
return;
}

container.style.display='block';
var meeting=prepState.meeting;
var isLoading=meeting.id==='_loading_';
var mins=meeting.minutes_until||0;
var countdownClass='hub-prep-meeting-countdown';
var countdownText='';
if(mins<=0){countdownText='Starting now';countdownClass+=' now';}
else if(mins<=15){countdownText='In '+mins+' min';countdownClass+=' soon';}
else if(mins<60){countdownText='In '+mins+' min';}
else{var hrs=Math.floor(mins/60);var m=mins%60;countdownText='In '+hrs+'h'+(m>0?' '+m+'m':'');}

subtitle.textContent=isLoading?'':meeting.title;

var html='<div class="hub-prep-meeting">';
html+='<div class="hub-prep-meeting-header">';
html+='<div class="hub-prep-meeting-info">';
if(isLoading){
html+='<div class="skeleton" style="height:18px;width:200px;margin-bottom:8px"></div>';
html+='<div class="skeleton" style="height:14px;width:120px"></div>';
}else{
html+='<div class="hub-prep-meeting-title">'+escapeHtml(meeting.title)+'</div>';
html+='<div class="hub-prep-meeting-details">';
html+='<div class="hub-prep-meeting-time"><svg viewBox="0 0 24 24"><path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"/></svg>'+escapeHtml(meeting.start_formatted||'')+'</div>';
html+='<div class="'+countdownClass+'">'+countdownText+'</div>';
html+='</div>';
}
html+='</div>';
if(meeting.meet_link&&!isLoading){
html+='<a href="'+meeting.meet_link+'" class="cal-join" target="_blank"><svg viewBox="0 0 24 24"><path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/></svg>Join</a>';
}
html+='</div></div>';

var totalItems=0;
var atlassianAuth=hubAuthStatus.atlassian||{};
var slackAuth=hubAuthStatus.slack||{};
var sources=settings.hubSources||{};

// AI Summary section (at top) - collapsible
if(sources.aiBrief!==false){
var summaryCollapsed=localStorage.getItem('hub-summary-collapsed')==='true';
var hasContent=prepState.summary||prepState.loading.summary;
var summaryRefreshIcon='<svg viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>';
html+='<div class="hub-prep-section hub-prep-summary'+(summaryCollapsed?' collapsed':'')+'">';
html+='<div class="hub-prep-section-title'+(hasContent&&!summaryCollapsed?' has-content':'')+'" onclick="toggleSummary()">AI Brief<button class="hub-section-refresh'+(prepState.loading.summary?' loading':'')+'" onclick="event.stopPropagation();retrySource(\'summary\')" title="Refresh">'+summaryRefreshIcon+'</button></div>';
html+='<div class="hub-summary-body">';
if(prepState.loading.summary){
html+='<div class="skeleton-summary"><div class="skeleton skeleton-summary-line"></div><div class="skeleton skeleton-summary-line"></div><div class="skeleton skeleton-summary-line"></div></div>';
}else if(prepState.summary){
html+='<div class="hub-summary-content">'+formatSummary(prepState.summary)+'</div>';
}else{
html+='<div class="hub-section-empty"><span>No summary available</span><button class="hub-retry-btn" onclick="retrySource(\'summary\')">Try again</button></div>';
}
html+='</div></div>';
}

// Helper for skeleton items
function renderSkeletonItems(count){
var s='<div class="hub-items">';
for(var i=0;i<count;i++){
s+='<div class="skeleton-item"><div class="skeleton skeleton-icon"></div><div class="skeleton-content"><div class="skeleton skeleton-title"></div><div class="skeleton skeleton-text"></div></div></div>';
}
return s+'</div>';
}

// Helper for section title with subtle refresh button
function sectionTitle(name,source,loading){
var refreshIcon='<svg viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>';
return '<div class="hub-prep-section-title">'+name+'<button class="hub-section-refresh'+(loading?' loading':'')+'" onclick="event.stopPropagation();retrySource(\''+source+'\')" title="Refresh">'+refreshIcon+'</button></div>';
}

// Jira section
if(sources.jira!==false){
html+='<div class="hub-prep-section">'+sectionTitle('Jira','jira',prepState.loading.jira);
if(!atlassianAuth.configured){
html+='<div class="hub-section-empty">Not configured</div>';
}else if(atlassianAuth.error==='oauth_required'){
html+='<div class="hub-auth-error"><span class="hub-auth-icon">🔐</span><span>Authentication required</span><button class="hub-auth-btn" onclick="window.open(\'http://127.0.0.1:18765/hub/atlassian/oauth\',\'_blank\')">Connect Atlassian</button></div>';
}else if(!atlassianAuth.authenticated&&atlassianAuth.error){
html+='<div class="hub-auth-error"><span class="hub-auth-icon">⚠️</span><span>Auth error: '+escapeHtml(atlassianAuth.error)+'</span></div>';
}else if(prepState.loading.jira){
html+=renderSkeletonItems(3);
}else if(prepState.jira.length>0){
html+='<div class="hub-items">';
prepState.jira.forEach(function(item){html+=renderHubItem(item,'jira');});
html+='</div>';
totalItems+=prepState.jira.length;
}else{
html+='<div class="hub-section-empty"><span>No related issues found</span><button class="hub-retry-btn" onclick="retrySource(\'jira\')">Try again</button></div>';
}
html+='</div>';
}

// Confluence section
if(sources.confluence!==false){
html+='<div class="hub-prep-section">'+sectionTitle('Confluence','confluence',prepState.loading.confluence);
if(!atlassianAuth.configured){
html+='<div class="hub-section-empty">Not configured</div>';
}else if(atlassianAuth.error==='oauth_required'){
html+='<div class="hub-auth-error"><span class="hub-auth-icon">🔐</span><span>Authentication required</span><button class="hub-auth-btn" onclick="window.open(\'http://127.0.0.1:18765/hub/atlassian/oauth\',\'_blank\')">Connect Atlassian</button></div>';
}else if(!atlassianAuth.authenticated&&atlassianAuth.error){
html+='<div class="hub-auth-error"><span class="hub-auth-icon">⚠️</span><span>Auth error: '+escapeHtml(atlassianAuth.error)+'</span></div>';
}else if(prepState.loading.confluence){
html+=renderSkeletonItems(3);
}else if(prepState.confluence.length>0){
html+='<div class="hub-items">';
prepState.confluence.forEach(function(item){html+=renderHubItem(item,'confluence');});
html+='</div>';
totalItems+=prepState.confluence.length;
}else{
html+='<div class="hub-section-empty"><span>No related pages found</span><button class="hub-retry-btn" onclick="retrySource(\'confluence\')">Try again</button></div>';
}
html+='</div>';
}

// Google Drive section
if(sources.drive!==false){
html+='<div class="hub-prep-section">'+sectionTitle('Google Drive','drive',prepState.loading.drive);
if(prepState.loading.drive){
html+=renderSkeletonItems(2);
}else if(prepState.google_drive.length>0){
html+='<div class="hub-items">';
prepState.google_drive.forEach(function(item){html+=renderHubItem(item,'drive');});
html+='</div>';
totalItems+=prepState.google_drive.length;
}else{
html+='<div class="hub-section-empty"><span>No related files found</span><button class="hub-retry-btn" onclick="retrySource(\'drive\')">Try again</button></div>';
}
html+='</div>';
}

// Slack section (meeting-related messages)
if(sources.slack!==false){
html+='<div class="hub-prep-section">'+sectionTitle('Slack','slack',prepState.loading.slack);
if(!slackAuth.configured){
html+='<div class="hub-section-empty">Not configured</div>';
}else if(!slackAuth.authenticated&&slackAuth.error){
html+='<div class="hub-auth-error"><span class="hub-auth-icon">🔐</span><span>Token expired or invalid</span><div class="hub-auth-instructions">Get tokens from Slack in browser: <code>localStorage.localConfig_v2</code> → copy xoxc and xoxd tokens to MCP config</div></div>';
}else if(prepState.loading.slack){
html+=renderSkeletonItems(2);
}else if(prepState.slack.length>0){
html+='<div class="hub-items">';
prepState.slack.forEach(function(item){html+=renderHubItem(item,'slack');});
html+='</div>';
totalItems+=prepState.slack.length;
}else{
html+='<div class="hub-section-empty"><span>No related messages found</span><button class="hub-retry-btn" onclick="retrySource(\'slack\')">Try again</button></div>';
}
html+='</div>';
}

// Gmail section (meeting-related emails)
if(sources.gmail!==false){
html+='<div class="hub-prep-section">'+sectionTitle('Gmail','gmail',prepState.loading.gmail);
if(prepState.loading.gmail){
html+=renderSkeletonItems(2);
}else if(prepState.gmail.length>0){
html+='<div class="hub-items">';
prepState.gmail.forEach(function(item){html+=renderHubItem(item,'gmail');});
html+='</div>';
totalItems+=prepState.gmail.length;
}else{
html+='<div class="hub-section-empty"><span>No related emails found</span><button class="hub-retry-btn" onclick="retrySource(\'gmail\')">Try again</button></div>';
}
html+='</div>';
}

badge.textContent=totalItems>0?totalItems:'';
// Update collapsed badge
var collapsedBadge=document.getElementById('hub-prep-collapsed-badge');
if(collapsedBadge){
collapsedBadge.textContent=totalItems>0?totalItems:'';
collapsedBadge.classList.toggle('has-items',totalItems>0);
}
content.innerHTML=html;
}

function fetchMeetingPrep(){
currentMeetingIndex=0;
selectedDate=null;
// Fetch week data first, which will then load the first day's meetings
fetchWeekData();
}

function fetchMeetingPrepForIndex(index){
var container=document.getElementById('hub-prep');
var content=document.getElementById('hub-prep-content');
var sources=settings.hubSources||{};

// Reset state - set loading based on which sources are enabled
prepState={meeting:null,jira:[],confluence:[],google_drive:[],slack:[],gmail:[],summary:null,loading:{
jira:sources.jira!==false,
confluence:sources.confluence!==false,
drive:sources.drive!==false,
slack:sources.slack!==false,
gmail:sources.gmail!==false,
summary:sources.aiBrief!==false
}};

// Show skeleton loading state immediately (no UI jump)
container.style.display='block';
// Create a placeholder meeting for skeleton rendering
prepState.meeting={title:'Loading...',start_formatted:'',minutes_until:0,id:'_loading_'};
renderMeetingPrepProgressive();

// 1. First get meeting info (with index and date parameters)
var dateParam=selectedDate?'&date='+selectedDate:'';
fetch(S+'/hub/prep/meeting?index='+index+dateParam,{signal:AbortSignal.timeout(10000)})
.then(function(r){return r.json();})
.then(function(data){
if(!data.meeting){
container.style.display='none';
allMeetings=[];
updateMeetingNav();
return;
}
// Store all meetings and update navigation
allMeetings=data.all_meetings||[data.meeting];
currentMeetingIndex=data.index||0;
updateMeetingNav();

prepState.meeting=data.meeting;
renderMeetingPrepProgressive();

// Get meeting_id for API calls - also used to prevent race conditions
var mid = data.meeting.id || '';
var midParam = mid ? '?meeting_id=' + encodeURIComponent(mid) : '';

// Helper to check if response is still for current meeting (prevents race conditions)
function isStillCurrentMeeting(){return prepState.meeting&&prepState.meeting.id===mid&&mid!=='_loading_';}

// Try batch endpoint first (single request for all cached data - instant!)
if(mid){
fetch(S+'/hub/prep/all'+midParam)
.then(function(r){return r.json();})
.then(function(cached){
if(!isStillCurrentMeeting())return; // Switched meetings - ignore stale response
if(cached.all_cached){
// All data is cached - instant load!
if(sources.jira!==false){prepState.jira=cached.jira||[];prepState.loading.jira=false;}
if(sources.confluence!==false){prepState.confluence=cached.confluence||[];prepState.loading.confluence=false;}
if(sources.drive!==false){prepState.google_drive=cached.drive||[];prepState.loading.drive=false;}
if(sources.slack!==false){prepState.slack=cached.slack||[];prepState.loading.slack=false;}
if(sources.gmail!==false){prepState.gmail=cached.gmail||[];prepState.loading.gmail=false;}
if(sources.aiBrief!==false){prepState.summary=cached.summary||null;prepState.loading.summary=false;}
renderMeetingPrepProgressive();
}else{
// Some sources not cached - fetch missing ones individually
if(sources.jira!==false){
if(cached.jira!==null){prepState.jira=cached.jira;prepState.loading.jira=false;renderMeetingPrepProgressive();}
else{fetch(S+'/hub/prep/jira'+midParam).then(function(r){return r.json();}).then(function(d){if(!isStillCurrentMeeting())return;prepState.jira=Array.isArray(d)?d:[];prepState.loading.jira=false;renderMeetingPrepProgressive();}).catch(function(){if(!isStillCurrentMeeting())return;prepState.loading.jira=false;renderMeetingPrepProgressive();});}
}
if(sources.confluence!==false){
if(cached.confluence!==null){prepState.confluence=cached.confluence;prepState.loading.confluence=false;renderMeetingPrepProgressive();}
else{fetch(S+'/hub/prep/confluence'+midParam).then(function(r){return r.json();}).then(function(d){if(!isStillCurrentMeeting())return;prepState.confluence=Array.isArray(d)?d:[];prepState.loading.confluence=false;renderMeetingPrepProgressive();}).catch(function(){if(!isStillCurrentMeeting())return;prepState.loading.confluence=false;renderMeetingPrepProgressive();});}
}
if(sources.drive!==false){
if(cached.drive!==null){prepState.google_drive=cached.drive;prepState.loading.drive=false;renderMeetingPrepProgressive();}
else{fetch(S+'/hub/prep/drive'+midParam).then(function(r){return r.json();}).then(function(d){if(!isStillCurrentMeeting())return;prepState.google_drive=Array.isArray(d)?d:[];prepState.loading.drive=false;renderMeetingPrepProgressive();}).catch(function(){if(!isStillCurrentMeeting())return;prepState.loading.drive=false;renderMeetingPrepProgressive();});}
}
if(sources.slack!==false){
if(cached.slack!==null){prepState.slack=cached.slack;prepState.loading.slack=false;renderMeetingPrepProgressive();}
else{fetch(S+'/hub/prep/slack'+midParam).then(function(r){return r.json();}).then(function(d){if(!isStillCurrentMeeting())return;prepState.slack=Array.isArray(d)?d:[];prepState.loading.slack=false;renderMeetingPrepProgressive();}).catch(function(){if(!isStillCurrentMeeting())return;prepState.loading.slack=false;renderMeetingPrepProgressive();});}
}
if(sources.gmail!==false){
if(cached.gmail!==null){prepState.gmail=cached.gmail;prepState.loading.gmail=false;renderMeetingPrepProgressive();}
else{fetch(S+'/hub/prep/gmail'+midParam).then(function(r){return r.json();}).then(function(d){if(!isStillCurrentMeeting())return;prepState.gmail=Array.isArray(d)?d:[];prepState.loading.gmail=false;renderMeetingPrepProgressive();}).catch(function(){if(!isStillCurrentMeeting())return;prepState.loading.gmail=false;renderMeetingPrepProgressive();});}
}
if(sources.aiBrief!==false){
if(cached.summary!==null){prepState.summary=cached.summary;prepState.loading.summary=false;renderMeetingPrepProgressive();}
else{fetch(S+'/hub/prep/summary'+midParam).then(function(r){return r.json();}).then(function(d){if(!isStillCurrentMeeting())return;prepState.summary=d.summary||null;prepState.loading.summary=false;renderMeetingPrepProgressive();}).catch(function(){if(!isStillCurrentMeeting())return;prepState.loading.summary=false;renderMeetingPrepProgressive();});}
}
}
})
.catch(function(){
if(!isStillCurrentMeeting())return;
// Batch endpoint failed - fall back to individual fetches
fetchSourcesIndividually(midParam,sources,isStillCurrentMeeting);
});
}else{
// No meeting_id - fetch individually
fetchSourcesIndividually(midParam,sources,function(){return true;});
}
})
.catch(function(e){
console.log('Meeting prep error:',e);
container.style.display='none';
});
}

function fetchSourcesIndividually(midParam,sources,isStillCurrent){
// Fallback: fetch each source individually with race condition protection
var check=isStillCurrent||function(){return true;};
if(sources.jira!==false){fetch(S+'/hub/prep/jira'+midParam).then(function(r){return r.json();}).then(function(d){if(!check())return;prepState.jira=Array.isArray(d)?d:[];prepState.loading.jira=false;renderMeetingPrepProgressive();}).catch(function(){if(!check())return;prepState.loading.jira=false;renderMeetingPrepProgressive();});}
if(sources.confluence!==false){fetch(S+'/hub/prep/confluence'+midParam).then(function(r){return r.json();}).then(function(d){if(!check())return;prepState.confluence=Array.isArray(d)?d:[];prepState.loading.confluence=false;renderMeetingPrepProgressive();}).catch(function(){if(!check())return;prepState.loading.confluence=false;renderMeetingPrepProgressive();});}
if(sources.drive!==false){fetch(S+'/hub/prep/drive'+midParam).then(function(r){return r.json();}).then(function(d){if(!check())return;prepState.google_drive=Array.isArray(d)?d:[];prepState.loading.drive=false;renderMeetingPrepProgressive();}).catch(function(){if(!check())return;prepState.loading.drive=false;renderMeetingPrepProgressive();});}
if(sources.slack!==false){fetch(S+'/hub/prep/slack'+midParam).then(function(r){return r.json();}).then(function(d){if(!check())return;prepState.slack=Array.isArray(d)?d:[];prepState.loading.slack=false;renderMeetingPrepProgressive();}).catch(function(){if(!check())return;prepState.loading.slack=false;renderMeetingPrepProgressive();});}
if(sources.gmail!==false){fetch(S+'/hub/prep/gmail'+midParam).then(function(r){return r.json();}).then(function(d){if(!check())return;prepState.gmail=Array.isArray(d)?d:[];prepState.loading.gmail=false;renderMeetingPrepProgressive();}).catch(function(){if(!check())return;prepState.loading.gmail=false;renderMeetingPrepProgressive();});}
if(sources.aiBrief!==false){fetch(S+'/hub/prep/summary'+midParam).then(function(r){return r.json();}).then(function(d){if(!check())return;prepState.summary=d.summary||null;prepState.loading.summary=false;renderMeetingPrepProgressive();}).catch(function(){if(!check())return;prepState.loading.summary=false;renderMeetingPrepProgressive();});}
}

function toggleSummary(){
var el=document.querySelector('.hub-prep-summary');
if(!el)return;
var isCollapsed=el.classList.toggle('collapsed');
localStorage.setItem('hub-summary-collapsed',isCollapsed);
// Update title margin based on collapsed state
var title=el.querySelector('.hub-prep-section-title');
if(title){
if(isCollapsed){
title.classList.remove('has-content');
}else if(prepState.summary||prepState.loading.summary){
title.classList.add('has-content');
}
}
}

function retrySource(source){
// Map source to prepState key and endpoint
var sourceMap={
'jira':{key:'jira',endpoint:'/hub/prep/jira'},
'confluence':{key:'confluence',endpoint:'/hub/prep/confluence'},
'drive':{key:'google_drive',endpoint:'/hub/prep/drive'},
'slack':{key:'slack',endpoint:'/hub/prep/slack'},
'gmail':{key:'gmail',endpoint:'/hub/prep/gmail'},
'summary':{key:'summary',endpoint:'/hub/prep/summary'}
};
var cfg=sourceMap[source];
if(!cfg)return;

// Don't retry if meeting is still loading
var mid=prepState.meeting&&prepState.meeting.id?prepState.meeting.id:'';
if(!mid||mid==='_loading_'){
console.log('Cannot refresh - meeting still loading');
return;
}

// Set loading state
var loadingKey=source==='drive'?'drive':source;
prepState.loading[loadingKey]=true;
renderMeetingPrepProgressive();

// Build URL with meeting_id and refresh=1
var url=S+cfg.endpoint+'?refresh=1&meeting_id='+encodeURIComponent(mid);

// Capture meeting ID at request time for race condition check
var requestMid=mid;

// Fetch with refresh=1 to bypass cache
fetch(url)
.then(function(r){return r.json();})
.then(function(d){
// Only update if still on same meeting
if(prepState.meeting&&prepState.meeting.id!==requestMid){
console.log('Refresh response ignored - meeting changed');
return;
}
if(source==='summary'){
prepState.summary=d.summary||null;
}else{
prepState[cfg.key]=Array.isArray(d)?d:[];
}
prepState.loading[loadingKey]=false;
renderMeetingPrepProgressive();
})
.catch(function(e){
console.error('Refresh error for '+source+':',e);
if(prepState.meeting&&prepState.meeting.id!==requestMid)return;
prepState.loading[loadingKey]=false;
renderMeetingPrepProgressive();
});
}

var hubAuthStatus={slack:{},atlassian:{}};

function initHub(){
// Check if hub is enabled in settings
if(settings.hubEnabled===false){
var hubPanel=document.getElementById('hub-prep');
if(hubPanel)hubPanel.style.display='none';
return;
}

// Start loading prep widget immediately (don't wait for auth status)
if(settings.calEnabled){
fetchMeetingPrep();
}

// Fetch auth status in parallel (for error messages only)
fetch(S+'/hub/status')
.then(function(r){return r.json();})
.then(function(status){
console.log('Hub status:',status);
hubAuthStatus.slack=status.slack||{};
hubAuthStatus.atlassian=status.atlassian||{};
// Re-render to show any auth errors
if(prepState.meeting)renderMeetingPrepProgressive();
})
.catch(function(e){
console.log('Hub status error:',e);
});
}

// Initialize hub immediately (async calls won't block page render)
setTimeout(initHub,50);

// REMOVED: Slack Reply and Chat Panel Functions (using native Slack app instead)

function renderLogo(){
var logoEl=document.getElementById('logo');
var logoImg=logoEl.querySelector('img');
if(settings.logo){
logoImg.src=settings.logo;
logoEl.classList.add('show');
}else{
logoEl.classList.remove('show');
}
}
renderLogo();

function renderLinks(){
var h='';
settings.links.forEach(function(l){
if(l.image){
h+='<a href="'+l.url+'" class="q"><img src="'+l.image+'" alt="">'+l.name+'</a>';
}else{
h+='<a href="'+l.url+'" class="q"><svg viewBox="0 0 24 24"><path d="'+(l.icon||defaultIcon)+'"/></svg>'+l.name+'</a>';
}
});
ql.innerHTML=h;
}

function u(){var n=new Date(),h=n.getHours(),H=(h%12)||12,m=n.getMinutes();
t.innerHTML=H+'<span class="ts">:</span>'+(m<10?'0':'')+m;
var greeting=(h>=5&&h<12?'Good morning':h>=12&&h<17?'Good afternoon':h>=17&&h<21?'Good evening':'Good night');
g.textContent=settings.name?greeting+', '+settings.name:greeting;
d.textContent=W[n.getDay()]+', '+M[n.getMonth()]+' '+n.getDate();}

renderLinks();u();setInterval(u,1000);
// Aggressive focus to steal from browser URL bar
s.focus();
setTimeout(function(){s.focus();},50);
setTimeout(function(){s.focus();},150);
setTimeout(function(){s.focus();},300);

function R(a,q){if(!q){r.innerHTML='';r.classList.remove('a');return;}
var h='<a href="https://www.google.com/search?q='+encodeURIComponent(q)+'" class="su sug"><svg class="sui" viewBox="0 0 24 24" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg><span class="sut">Search Google for "'+q.replace(/</g,'&lt;')+'"</span><span class="suy">Google</span></a>';
for(var i=0;i<a.length;i++){var x=a[i],l=x.type==='bookmark'?'Saved':'History',v=x.visit_count||0,c=x.type==='bookmark'?'<svg class="sui" viewBox="0 0 24 24" fill="currentColor"><path d="M17 3H7c-1.1 0-2 .9-2 2v16l7-3 7 3V5c0-1.1-.9-2-2-2z"/></svg>':'<svg class="sui" viewBox="0 0 24 24" fill="currentColor"><path d="M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.95 8.95 0 0013 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z"/></svg>';
h+='<a href="'+x.url+'" class="su">'+c+'<span class="sut">'+(x.title||'').replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</span><span class="suy">'+l+'</span>'+(v>1?'<span class="suv">'+v+'×</span>':'')+'</a>';}
r.innerHTML=h;r.classList.add('a');I=-1;}

s.oninput=function(e){var q=e.target.value.trim();clearTimeout(D);if(!q){R([],'');return;}
D=setTimeout(function(){fetch(S+'/search?q='+encodeURIComponent(q),{signal:AbortSignal.timeout(2000)}).then(function(x){return x.ok?x.json():[];}).catch(function(){return[];}).then(function(a){R(a,q);});},300);};

s.onkeydown=function(e){var a=r.querySelectorAll('.su');
if(e.key==='ArrowDown'){e.preventDefault();I=Math.min(I+1,a.length-1);for(var i=0;i<a.length;i++)a[i].classList.toggle('sl',i===I);}
else if(e.key==='ArrowUp'){e.preventDefault();I=Math.max(I-1,-1);for(var i=0;i<a.length;i++)a[i].classList.toggle('sl',i===I);}
else if(e.key==='Enter'){if(I>=0&&a[I])location.href=a[I].href;else if(s.value.trim()){var v=s.value.trim();if(/^https?:\/\//i.test(v))location.href=v;else if(/^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z]{2,})+/i.test(v))location.href='https://'+v;else location.href='https://www.google.com/search?q='+encodeURIComponent(v);}}
else if(e.key==='Escape'){r.classList.remove('a');I=-1;}};

document.onclick=function(e){if(!e.target.closest('.sc')&&!e.target.closest('.modal'))r.classList.remove('a');};
document.onkeydown=function(e){
if(e.key==='Escape'&&document.getElementById('modal').classList.contains('show')){closeModal();return;}
if(e.key.length===1&&!e.metaKey&&!e.ctrlKey&&document.activeElement!==s&&!document.getElementById('modal').classList.contains('show')&&document.activeElement.tagName!=='TEXTAREA')s.focus();
};

function openModal(){
document.getElementById('modal').classList.add('show');
document.getElementById('edit-name').value=settings.name||'';
document.getElementById('cal-enabled').checked=settings.calEnabled||false;
document.getElementById('cal-minutes').value=settings.calMinutes||60;
document.getElementById('cal-settings-fields').style.display=settings.calEnabled?'block':'none';
renderLogoPreview();
renderBgPresets();
updateThemeButtons();
renderLinkEditor();
populateHubSettings();
switchSettingsTab('general');
}
function renderLogoPreview(){
var preview=document.getElementById('logo-preview');
if(settings.logo){
preview.innerHTML='<img src="'+settings.logo+'" alt="">';
}else{
preview.innerHTML='<svg viewBox="0 0 24 24"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>';
}
}
function handleLogoUpload(input){
var file=input.files[0];
if(!file)return;
if(file.size>500000){alert('Image too large. Please use an image under 500KB.');return;}
var reader=new FileReader();
reader.onload=function(e){
settings.logo=e.target.result;
renderLogoPreview();
renderLogo();
};
reader.readAsDataURL(file);
}
function clearLogo(){
settings.logo='';
renderLogoPreview();
renderLogo();
}
function closeModal(){
document.getElementById('modal').classList.remove('show');
s.focus();
}
function renderBgPresets(){
var c=document.getElementById('bg-presets');
var h='';
gradients.forEach(function(gr,i){
var active=(settings.bg===gr.value)?'active':'';
h+='<div class="bg-swatch '+active+'" style="background:'+gr.value+'" onclick="selectGradient('+i+')" title="'+gr.name+'"></div>';
});
if(settings.bg&&settings.bg.startsWith('data:')){
h+='<div class="bg-preview" style="background-image:url('+settings.bg+')"></div>';
}
c.innerHTML=h;
updateGradientPreview();
}
function updateGradientPreview(){
var c1=document.getElementById('color1');
var c2=document.getElementById('color2');
var preview=document.getElementById('gradient-preview');
if(c1&&c2&&preview){
preview.style.background='linear-gradient(135deg,'+c1.value+' 0%,'+c2.value+' 100%)';
}
}
function applyCustomGradient(){
var c1=document.getElementById('color1').value;
var c2=document.getElementById('color2').value;
settings.bg='linear-gradient(135deg,'+c1+' 0%,'+c2+' 100%)';
applyBg();
renderBgPresets();
}
function selectGradient(i){
settings.bg=gradients[i].value;
applyBg();
renderBgPresets();
}
function handleBgUpload(input){
var file=input.files[0];
if(!file)return;
if(file.size>2000000){alert('Image too large. Please use an image under 2MB.');return;}
var reader=new FileReader();
reader.onload=function(e){
settings.bg=e.target.result;
applyBg();
renderBgPresets();
};
reader.readAsDataURL(file);
}
function clearBg(){
settings.bg=gradients[0].value;
applyBg();
renderBgPresets();
}
function renderLinkEditor(){
var c=document.getElementById('links-container');
var h='';
settings.links.forEach(function(l,i){
var iconPreview=l.image?
'<img src="'+l.image+'" alt="">':
'<svg viewBox="0 0 24 24"><path d="'+(l.icon||defaultIcon)+'"/></svg>';
h+='<div class="link-item">'+
'<div>'+
'<div class="link-icon" onclick="triggerUpload('+i+')" title="Click to upload icon">'+iconPreview+'</div>'+
'<div class="icon-hint">Click to change</div>'+
'</div>'+
'<input type="file" id="file-'+i+'" accept="image/*" onchange="handleUpload('+i+',this)">'+
'<div class="link-fields">'+
'<input type="text" value="'+escapeHtml(l.name)+'" placeholder="Name" onchange="updateLink('+i+',\'name\',this.value)">'+
'<input type="text" value="'+escapeHtml(l.url)+'" placeholder="URL" onchange="updateLink('+i+',\'url\',this.value)">'+
'</div>'+
'<button class="link-remove" onclick="removeLink('+i+')" title="Remove">×</button>'+
'</div>';
});
c.innerHTML=h;
}
function escapeHtml(str){return (str||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function triggerUpload(i){document.getElementById('file-'+i).click();}
function handleUpload(i,input){
var file=input.files[0];
if(!file)return;
if(file.size>500000){alert('Image too large. Please use an image under 500KB.');return;}
var reader=new FileReader();
reader.onload=function(e){
settings.links[i].image=e.target.result;
delete settings.links[i].icon;
renderLinkEditor();
};
reader.readAsDataURL(file);
}
function updateLink(i,field,value){settings.links[i][field]=value;}
function removeLink(i){settings.links.splice(i,1);renderLinkEditor();}
function addLink(){
settings.links.push({name:'New',url:'https://',icon:defaultIcon});
renderLinkEditor();
}
function saveSettings(){
settings.name=document.getElementById('edit-name').value.trim();
settings.calEnabled=document.getElementById('cal-enabled').checked;
settings.calMinutes=parseInt(document.getElementById('cal-minutes').value)||60;
settings.hubEnabled=document.getElementById('hub-enabled').checked;
settings.hubSources={
jira:document.getElementById('hub-jira').checked,
confluence:document.getElementById('hub-confluence').checked,
slack:document.getElementById('hub-slack').checked,
gmail:document.getElementById('hub-gmail').checked,
drive:document.getElementById('hub-drive').checked,
aiBrief:document.getElementById('hub-ai-brief').checked
};
saveToStorage(settings);
renderLinks();
u();
if(settings.calEnabled){
fetchCalendar();
}else{
document.getElementById('cal-container').classList.remove('show');
}
applyHubSettings();
closeModal();
}
function applyHubSettings(){
var hubPanel=document.getElementById('hub-prep');
if(hubPanel){
if(settings.hubEnabled){
initHub();
}else{
hubPanel.style.display='none';
}
}
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
