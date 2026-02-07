// BriefDesk - Core App
// Themes, settings, calendar, search, time display

var darkTheme={
'--text-primary':'rgba(255,255,255,.9)',
'--text-secondary':'rgba(255,255,255,.7)',
'--text-muted':'rgba(255,255,255,.5)',
'--text-greeting':'rgba(255,255,255,.8)',
'--text-time':'#fff',
'--text-date':'rgba(255,255,255,.5)',
'--bg-card':'rgba(0,0,0,.3)',
'--bg-card-hover':'rgba(255,255,255,.1)',
'--border-color':'rgba(255,255,255,.15)',
'--border-hover':'rgba(255,255,255,.25)'
};
var lightTheme={
'--text-primary':'rgba(0,0,0,.85)',
'--text-secondary':'rgba(0,0,0,.7)',
'--text-muted':'rgba(0,0,0,.5)',
'--text-greeting':'rgba(0,0,0,.7)',
'--text-time':'rgba(0,0,0,.85)',
'--text-date':'rgba(0,0,0,.5)',
'--bg-card':'rgba(255,255,255,.75)',
'--bg-card-hover':'rgba(0,0,0,.08)',
'--border-color':'rgba(0,0,0,.12)',
'--border-hover':'rgba(0,0,0,.2)'
};

var defaultIcon='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z';
var defaultLinks=[
{name:'Mail',url:'https://mail.google.com',icon:'M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z'},
{name:'Calendar',url:'https://calendar.google.com',icon:'M19 3h-1V1h-2v2H8V1H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM9 10H7v2h2v-2zm4 0h-2v2h2v-2zm4 0h-2v2h2v-2zm-8 4H7v2h2v-2zm4 0h-2v2h2v-2zm4 0h-2v2h2v-2z'},
{name:'Drive',url:'https://drive.google.com',icon:'M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z'},
{name:'GitHub',url:'https://github.com',icon:'M12 0C5.37 0 0 5.37 0 12c0 5.3 3.44 9.8 8.21 11.39.6.11.79-.26.79-.58v-2.23c-3.34.73-4.03-1.42-4.03-1.42-.55-1.39-1.33-1.76-1.33-1.76-1.09-.74.08-.73.08-.73 1.2.08 1.84 1.24 1.84 1.24 1.07 1.83 2.81 1.3 3.49 1 .11-.78.42-1.3.76-1.6-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.18 0 0 1.01-.32 3.3 1.23.96-.27 1.98-.4 3-.4s2.04.13 3 .4c2.29-1.55 3.3-1.23 3.3-1.23.66 1.66.24 2.88.12 3.18.77.84 1.24 1.91 1.24 3.22 0 4.61-2.81 5.62-5.48 5.92.43.37.82 1.1.82 2.22v3.29c0 .32.19.69.8.58C20.57 21.8 24 17.3 24 12c0-6.63-5.37-12-12-12z'}
];
var gradients=[
{name:'Midnight',value:'linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%)'},
{name:'Ocean',value:'linear-gradient(135deg,#0f2027 0%,#203a43 50%,#2c5364 100%)'},
{name:'Sunset',value:'linear-gradient(135deg,#232526 0%,#414345 50%,#232526 100%)'},
{name:'Purple',value:'linear-gradient(135deg,#1a1a2e 0%,#2d1b4e 50%,#1a1a2e 100%)'},
{name:'Forest',value:'linear-gradient(135deg,#0d1b0e 0%,#1a3a1c 50%,#0d1b0e 100%)'},
{name:'Warm',value:'linear-gradient(135deg,#2c1810 0%,#3d2317 50%,#1a0f0a 100%)'},
{name:'Nord',value:'linear-gradient(135deg,#2e3440 0%,#3b4252 50%,#2e3440 100%)'},
{name:'Rose',value:'linear-gradient(135deg,#1a1a2e 0%,#2e1a2e 50%,#1a1a2e 100%)'}
];

function getSettings(){
var s=localStorage.getItem('startpage');
var defaultHubSources={jira:true,confluence:true,slack:true,gmail:true,drive:true,github:true,aiBrief:true};
if(s){try{var p=JSON.parse(s);if(!p.theme)p.theme='dark';if(p.hubEnabled===undefined)p.hubEnabled=true;if(!p.hubSources)p.hubSources=defaultHubSources;return p;}catch(e){}}
return {name:'',links:defaultLinks,bg:gradients[0].value,theme:'dark',logo:'',calEnabled:false,calUrl:'',calMinutes:60,hubEnabled:true,hubSources:defaultHubSources,hubModel:'anthropic-claude-4-5-haiku'};
}
function saveToStorage(settings){localStorage.setItem('startpage',JSON.stringify(settings));}

var settings=getSettings();
var g=document.getElementById('g'),t=document.getElementById('t'),d=document.getElementById('d'),s=document.getElementById('s'),r=document.getElementById('r'),ql=document.getElementById('ql'),S='http://127.0.0.1:18765',SEARCH_SERVICE='http://127.0.0.1:19765',D,I=-1,W=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'],M=['January','February','March','April','May','June','July','August','September','October','November','December'];

function applyTheme(){
var theme=settings.theme==='light'?lightTheme:darkTheme;
var root=document.documentElement;
for(var k in theme){root.style.setProperty(k,theme[k]);}
}
function setTheme(theme){
settings.theme=theme;
applyTheme();
updateThemeButtons();
}
function updateThemeButtons(){
var dk=document.getElementById('theme-dark');
var lt=document.getElementById('theme-light');
if(dk&&lt){
dk.classList.toggle('active',settings.theme==='dark');
lt.classList.toggle('active',settings.theme==='light');
}
}
function applyBg(){
var bg=settings.bg||gradients[0].value;
if(bg.startsWith('data:')||bg.startsWith('http')){
document.body.style.background='url('+bg+') center/cover no-repeat fixed';
}else{
document.body.style.background=bg;
}
}

applyBg();
applyTheme();

// Calendar functions
var calendarExpanded=false;
var calendarCache=null;
try{calendarCache=JSON.parse(localStorage.getItem('calCache'));}catch(e){}
function renderCalendarData(data){
var container=document.getElementById('cal-container');
var inCallEl=document.getElementById('cal-in-call');
var eventsEl=document.getElementById('cal-events');
// Check for auth error and show banner
if(data.auth_error){
container.classList.add('show');
eventsEl.innerHTML='<div class="cal-auth-error" onclick="window.open(\'http://127.0.0.1:8765/installer.html\',\'_blank\')"><svg viewBox="0 0 24 24" style="width:16px;height:16px;fill:#f59e0b;margin-right:8px;flex-shrink:0"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg><span>Calendar auth expired. <u>Click to re-authenticate</u></span></div>';
return;
}
if(data.error&&!data.events){container.classList.remove('show');return;}
container.classList.add('show');
var events=data.events||[];
var inMeeting=data.in_meeting;
// Support both current_meetings array and legacy current_meeting
var currentMeetings=data.current_meetings||[];
if(!currentMeetings.length&&data.current_meeting){currentMeetings=[data.current_meeting];}
if(inMeeting&&currentMeetings.length>0){
inCallEl.style.display='flex';
// Show first meeting title, or count if multiple
if(currentMeetings.length===1){
document.getElementById('cal-current-title').textContent=currentMeetings[0].title;
}else{
document.getElementById('cal-current-title').textContent=currentMeetings.length+' meetings now';
}
var totalUpcoming=events.length+currentMeetings.length-1;
document.getElementById('cal-upcoming-count').textContent=totalUpcoming>0?'+'+totalUpcoming+' more':'';
// Add join button to in-call bar if first meeting has a link
var inCallJoin=document.getElementById('cal-in-call-join');
if(inCallJoin){
if(currentMeetings[0].meet_link){
inCallJoin.href=currentMeetings[0].meet_link;
inCallJoin.style.display='flex';
}else{
inCallJoin.style.display='none';
}
}
eventsEl.classList.toggle('collapsed',!calendarExpanded);
}else{
inCallEl.style.display='none';
eventsEl.classList.remove('collapsed');
calendarExpanded=false;
inCallEl.classList.remove('expanded');
}
// Combine ALL current meetings and future events for the list
var allEvents=[];
currentMeetings.forEach(function(m){allEvents.push(m);});
events.forEach(function(e){allEvents.push(e);});
if(allEvents.length===0&&!inMeeting){eventsEl.innerHTML='<div class="cal-empty">No upcoming meetings</div>';return;}
if(allEvents.length===0){eventsEl.innerHTML='';return;}
var html='';
allEvents.forEach(function(evt){
var mins=evt.minutes_until;
var countdownClass='cal-countdown';
var countdownText='';
if(evt.is_current||mins<=0){countdownText='Now';countdownClass='cal-countdown now';}
else if(mins<=5){countdownText='In '+mins+' min';countdownClass='cal-countdown soon';}
else if(mins<60){countdownText='In '+mins+' min';}
else{var hrs=Math.floor(mins/60);var m=mins%60;countdownText='In '+hrs+'h'+(m>0?' '+m+'m':'');}
var joinHtml=evt.meet_link?'<a href="'+evt.meet_link+'" class="cal-join" target="_blank"><svg viewBox="0 0 24 24"><path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/></svg>Join</a>':'';
html+='<div class="cal-card'+(evt.is_current?' cal-current':'')+'"><div class="cal-card-inner">';
html+='<div class="cal-icon"><svg viewBox="0 0 24 24"><path d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2zm-7 5h5v5h-5v-5z"/></svg></div>';
html+='<div class="cal-info"><div class="cal-title">'+evt.title+'</div>';
html+='<div class="cal-meta"><span class="cal-time">'+evt.start_formatted+'</span><span class="'+countdownClass+'">'+countdownText+'</span></div></div>';
html+=joinHtml+'</div></div>';
});
eventsEl.innerHTML=html;
}
function fetchCalendar(forceRefresh){
if(!settings.calEnabled){return;}
var container=document.getElementById('cal-container');
var eventsEl=document.getElementById('cal-events');
var refreshBtn=document.getElementById('cal-refresh-btn');
// Show cached data immediately, or loading indicator
if(calendarCache && !forceRefresh){
renderCalendarData(calendarCache);
}else{
container.classList.add('show');
if(!forceRefresh)eventsEl.innerHTML='<div class="cal-loading"><div class="cal-spinner"></div><span class="cal-loading-text">Loading calendar...</span></div>';
}
if(refreshBtn)refreshBtn.classList.add('spinning');
var url=S+'/calendar?minutes='+(settings.calMinutes||180)+'&limit=3'+(forceRefresh?'&refresh=1':'');
fetch(url,{signal:AbortSignal.timeout(10000)})
.then(function(r){return r.json();})
.then(function(data){
calendarCache=data;
try{localStorage.setItem('calCache',JSON.stringify(data));}catch(e){}
renderCalendarData(data);
if(refreshBtn)refreshBtn.classList.remove('spinning');
})
.catch(function(e){
console.log('Calendar error:',e);
document.getElementById('cal-container').classList.remove('show');
if(refreshBtn)refreshBtn.classList.remove('spinning');
});
}
function refreshCalendar(){
fetchCalendar(true);
}
function toggleCalendarExpand(){
calendarExpanded=!calendarExpanded;
document.getElementById('cal-events').classList.toggle('collapsed',!calendarExpanded);
document.getElementById('cal-in-call').classList.toggle('expanded',calendarExpanded);
}
function toggleCalendar(){
var enabled=document.getElementById('cal-enabled').checked;
settings.calEnabled=enabled;
document.getElementById('cal-settings-fields').style.display=enabled?'block':'none';
if(!enabled)document.getElementById('cal-container').classList.remove('show');
}
function switchSettingsTab(tab){
document.querySelectorAll('.settings-tab').forEach(function(t){t.classList.remove('active');});
document.querySelectorAll('.settings-panel').forEach(function(p){p.classList.remove('active');});
document.querySelector('[data-tab="'+tab+'"]').classList.add('active');
document.getElementById('settings-'+tab).classList.add('active');
}
function toggleHubSettings(){
var enabled=document.getElementById('hub-enabled').checked;
var container=document.getElementById('hub-sources-container');
if(enabled){
container.classList.remove('hub-sources-disabled');
}else{
container.classList.add('hub-sources-disabled');
}
}
function populateHubSettings(){
document.getElementById('hub-enabled').checked=settings.hubEnabled!==false;
var sources=settings.hubSources||{};
document.getElementById('hub-ai-brief').checked=sources.aiBrief!==false;
document.getElementById('hub-jira').checked=sources.jira!==false;
document.getElementById('hub-confluence').checked=sources.confluence!==false;
document.getElementById('hub-slack').checked=sources.slack!==false;
document.getElementById('hub-gmail').checked=sources.gmail!==false;
document.getElementById('hub-drive').checked=sources.drive!==false;
document.getElementById('hub-github').checked=sources.github!==false;
var safariEl=document.getElementById('safari-history-enabled');
if(safariEl){
safariEl.checked=!!settings.safariEnabled;
var fdaInstr=document.getElementById('safari-fda-instructions');
if(fdaInstr) fdaInstr.style.display=settings.safariEnabled?'block':'none';
var fdaStatus=document.getElementById('safari-fda-status');
if(fdaStatus){fdaStatus.textContent=settings.safariEnabled?'Enabled':'Disabled';fdaStatus.className=settings.safariEnabled?'hub-source-status connected':'hub-source-status disabled';}
if(settings.safariEnabled){fetch(S+'/installer/system-info').then(function(r){return r.json()}).then(function(d){var el=document.getElementById('safari-python-path');if(el&&d.python_real_path)el.textContent=d.python_real_path;else if(el&&d.python_path)el.textContent=d.python_path;}).catch(function(){});}
}
document.getElementById('hub-model').value=settings.hubModel||'gpt-4o';
toggleHubSettings();
fetchHubAuthStatus();
}
function updateHubModel(){
var model=document.getElementById('hub-model').value;
settings.hubModel=model;
saveToStorage(settings);
// Don't sync AI search model - it's independent (session-only)
// Reset session model so next AI search open will use new hub default
aiSearchSessionModel=null;
// Notify backend of model change (for hub/meeting prep)
fetch(S+'/hub/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:model})}).catch(function(){});
}
// Session-only AI search model (doesn't affect hub default)
var aiSearchSessionModel=null;
function updateAISearchModel(){
var model=document.getElementById('ai-search-model').value;
// Store in session only - don't update settings.hubModel or sync with hub
aiSearchSessionModel=model;
// Update provider logo
updateAIModelLogo();
}
function updateAIModelLogo(){
var select=document.getElementById('ai-search-model');
var logo=document.getElementById('ai-model-logo');
if(!select||!logo)return;
var opt=select.options[select.selectedIndex];
var provider=opt?opt.getAttribute('data-provider'):'anthropic';
logo.className='ai-model-logo '+(provider||'anthropic');
}
function fetchHubAuthStatus(){
fetch(S+'/hub/status',{signal:AbortSignal.timeout(5000)})
.then(function(r){return r.json();})
.then(function(status){
var atlassian=status.atlassian||{};
var slack=status.slack||{};
var gmail=status.gmail||{};
var drive=status.drive||{};
var needsSetup=[];
updateSourceStatus('hub-jira-status',atlassian.authenticated,atlassian.configured,atlassian.error);
updateSourceStatus('hub-confluence-status',atlassian.authenticated,atlassian.configured,atlassian.error);
if(!atlassian.authenticated&&atlassian.configured)needsSetup.push('atlassian');
else if(!atlassian.configured)needsSetup.push('atlassian-config');
updateSourceStatus('hub-slack-status',slack.authenticated,slack.configured,slack.error);
if(!slack.authenticated&&slack.configured)needsSetup.push('slack');
else if(!slack.configured)needsSetup.push('slack-config');
updateSourceStatus('hub-gmail-status',gmail.authenticated,gmail.configured,gmail.error);
if(!gmail.authenticated)needsSetup.push('gmail');
updateSourceStatus('hub-drive-status',drive.authenticated,drive.configured,drive.error);
if(!drive.authenticated)needsSetup.push('drive');
// GitHub status from hub auth response
var gh=status.github||{};
updateSourceStatus('hub-github-status',gh.authenticated,gh.configured);
showSetupHints(needsSetup);
})
.catch(function(){
['hub-jira-status','hub-confluence-status','hub-slack-status','hub-gmail-status','hub-drive-status'].forEach(function(id){
var el=document.getElementById(id);
if(el){el.textContent='Unknown';el.className='hub-source-status warning';}
});
});
}
function updateSourceStatus(id,authenticated,configured,error){
var el=document.getElementById(id);
if(!el)return;
if(authenticated){
el.textContent='Connected';
el.className='hub-source-status connected';
}else if(error){
var msg=error;
if(typeof msg==='string'){
if(msg.indexOf('Not authenticated')!==-1||msg.indexOf('auth_required')!==-1){
el.textContent='Auth required';
}else if(msg.indexOf('tool not found')!==-1){
el.textContent='Not configured';
}else if(msg.indexOf('search_service_unreachable')!==-1){
el.textContent='Unavailable';
}else{
el.textContent='Error';
}
}else{
el.textContent='Error';
}
el.className='hub-source-status warning';
}else if(configured){
el.textContent='Setup needed';
el.className='hub-source-status warning';
}else{
el.textContent='Not configured';
el.className='hub-source-status warning';
}
}
function showSetupHints(needsSetup){
var hint=document.getElementById('hub-setup-hint');
if(!hint)return;
if(needsSetup.length===0){hint.style.display='none';return;}
var html='<strong>Setup Instructions:</strong><br>';
if(needsSetup.indexOf('gmail')>=0){
html+='<br><strong>Gmail:</strong> Open the installer and click <em>Connect Gmail</em>.';
}
if(needsSetup.indexOf('drive')>=0){
html+='<br><strong>Google Drive:</strong> Open the installer and click <em>Connect Drive</em>.';
}
if(needsSetup.indexOf('atlassian')>=0||needsSetup.indexOf('atlassian-config')>=0){
html+='<br><strong>Atlassian (Jira/Confluence):</strong> Add <code>mcp-remote https://mcp.atlassian.com/v1/sse</code> to <code>.devsai.json</code>. OAuth will prompt on first use.';
}
if(needsSetup.indexOf('slack')>=0||needsSetup.indexOf('slack-config')>=0){
html+='<br><strong>Slack:</strong> Add slack-mcp-server to <code>.devsai.json</code> with xoxc/xoxd tokens from Slack web app localStorage.';
}
hint.innerHTML=html;
hint.style.display='block';
}
if(settings.calEnabled){
fetchCalendar();
setInterval(fetchCalendar,60000);
}

// =============================================================================
// AI Search
// =============================================================================
var aiSearchOpen=false;
var aiSearchSources={slack:true,jira:true,confluence:true,gmail:true,drive:true,github:true};
var aiSearchAbort=null;

function openAISearch(){
if(aiSearchOpen)return;
aiSearchOpen=true;
var overlay=document.getElementById('ai-search-overlay');
var mainSearch=document.getElementById('s');
overlay.classList.add('show');
// Sync model picker: use session model if set, otherwise use hub default
var aiModelPicker=document.getElementById('ai-search-model');
if(aiModelPicker){
// Only set to hub default if no session model has been selected
if(!aiSearchSessionModel&&settings.hubModel){
aiModelPicker.value=settings.hubModel;
}else if(aiSearchSessionModel){
aiModelPicker.value=aiSearchSessionModel;
}
}
updateAIModelLogo();
// Blur main search and focus AI search
if(mainSearch)mainSearch.blur();
setTimeout(function(){
var aiInput=document.getElementById('ai-search-input');
if(aiInput){aiInput.value='';aiInput.focus();}
},50);
document.body.style.overflow='hidden';
}

function closeAISearch(){
if(!aiSearchOpen)return;
aiSearchOpen=false;
var overlay=document.getElementById('ai-search-overlay');
overlay.classList.remove('show');
document.body.style.overflow='';
if(aiSearchAbort){aiSearchAbort.abort();aiSearchAbort=null;}
// Reset results
setTimeout(function(){
showAIEmpty();
},300);
}

function toggleAISource(source){
var pill=document.querySelector('.ai-source-pill[data-source="'+source+'"]');
aiSearchSources[source]=!aiSearchSources[source];
pill.classList.toggle('active');
}

function getActiveSources(){
var sources=[];
if(aiSearchSources.slack)sources.push('slack');
if(aiSearchSources.jira)sources.push('jira');
if(aiSearchSources.confluence)sources.push('confluence');
if(aiSearchSources.gmail)sources.push('gmail');
if(aiSearchSources.drive)sources.push('drive');
if(aiSearchSources.github)sources.push('github');
return sources;
}

var aiEventSource=null;
var aiProgressSteps=[];

function submitAISearch(){
var input=document.getElementById('ai-search-input');
var query=input.value.trim();
if(!query)return;
var sources=getActiveSources();
if(sources.length===0){
showAIError('Select at least one source');
return;
}

// Reset state
aiProgressSteps=[];
aiHasAddedResponding=false;
showAIProgress([]);

// Close any existing connection
if(aiEventSource){
aiEventSource.close();
aiEventSource=null;
}

// Use SSE for streaming progress
aiEventSource=new EventSource(S+'/hub/ai-search-stream?'+new URLSearchParams({
query:query,
sources:sources.join(',')
}));

// Actually, EventSource only does GET. Let's use fetch with streaming instead
aiEventSource.close();
aiEventSource=null;

// Use fetch with streaming response
if(aiSearchAbort)aiSearchAbort.abort();
aiSearchAbort=new AbortController();

// Get model from AI search picker (session-only, doesn't affect hub default)
var aiModel=document.getElementById('ai-search-model');
var modelToUse=aiModel?aiModel.value:(settings.hubModel||'gpt-4o');

fetch(S+'/hub/ai-search-stream',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({query:query,sources:sources,model:modelToUse}),
signal:aiSearchAbort.signal
}).then(function(response){
var reader=response.body.getReader();
var decoder=new TextDecoder();
var buffer='';

function processChunk(){
reader.read().then(function(result){
if(result.done){
return;
}
buffer+=decoder.decode(result.value,{stream:true});

// Parse SSE events from buffer
while(buffer.indexOf('\n\n')!==-1){
var idx=buffer.indexOf('\n\n');
var eventBlock=buffer.substring(0,idx);
buffer=buffer.substring(idx+2);

var eventType=null;
var eventData=null;
var lines=eventBlock.split('\n');
for(var i=0;i<lines.length;i++){
var line=lines[i];
if(line.indexOf('event: ')===0){
eventType=line.substring(7);
}else if(line.indexOf('data: ')===0){
try{
eventData=JSON.parse(line.substring(6));
}catch(e){
eventData={raw:line.substring(6)};
}
}
}

if(eventType&&eventData){
handleAIProgressEvent(eventType,eventData);
}
}

processChunk();
}).catch(function(e){
if(e.name!=='AbortError'){
console.error('Stream error:',e);
}
});
}
processChunk();
}).catch(function(e){
if(e.name!=='AbortError'){
showAIError('Search failed. Please try again.');
}
});
}

var aiHasAddedResponding=false;

function handleAIProgressEvent(eventType,data){
if(eventType==='progress'){
if(data.type==='thinking'){
addAIProgressStep('thinking','Thinking',null,'active');
}else if(data.type==='tool_start'){
addAIProgressStep('tool',data.description||data.tool,data.tool,'active');
}else if(data.type==='tool_complete'){
updateLastProgressStep(data.success?'complete':'error');
}else if(data.type==='content'&&!aiHasAddedResponding){
// AI is generating response
aiHasAddedResponding=true;
// Mark all previous steps as complete
for(var i=0;i<aiProgressSteps.length;i++){
if(aiProgressSteps[i].status==='active'){
aiProgressSteps[i].status='complete';
}
}
addAIProgressStep('responding','Responding',null,'active');
}else if(data.type==='done'){
// Mark responding as complete
updateLastProgressStep('complete');
}
}else if(eventType==='complete'){
// Brief delay to show completed state
setTimeout(function(){
showAIResponse(data.response,getActiveSources());
},300);
}else if(eventType==='error'){
if(data&&data.error==='auth_required'&&data.tool){
showAIError('Authentication required for '+data.tool.toUpperCase()+'.',data.tool);
}else{
showAIError(data.error||'Search failed');
}
}
}

var aiWorkflowExpanded=false;

function addAIProgressStep(type,text,tool,status){
// Build detailed step info
var label='',detail='';
if(type==='thinking'){
label='Analyzing';
detail='Processing query context';
}else if(type==='responding'){
label='Generating';
detail='Writing response';
}else if(type==='tool'){
var t=text.toLowerCase();
if(t.indexOf('slack')!==-1){
label='Slack';
detail=extractDetail(text,'messages');
}else if(t.indexOf('jira')!==-1){
label='Jira';
detail=extractDetail(text,'issues');
}else if(t.indexOf('confluence')!==-1){
label='Confluence';
detail=extractDetail(text,'pages');
}else if(t.indexOf('gmail')!==-1){
label='Gmail';
detail=extractDetail(text,'emails');
}else if(t.indexOf('drive')!==-1||t.indexOf('file')!==-1){
label='Drive';
detail=extractDetail(text,'files');
}else if(t.indexOf('atlassian')!==-1){
label='Atlassian';
detail='Fetching workspace info';
}else{
label='Search';
detail=text.length>40?text.substring(0,40)+'...':text;
}
}
aiProgressSteps.push({type:type,label:label,detail:detail,tool:tool,status:status});
showAIProgress(aiProgressSteps);
}

function extractDetail(text,fallback){
// Try to extract meaningful detail from tool description
var match=text.match(/["']([^"']+)["']/);
if(match)return'Searching "'+match[1]+'"';
if(text.indexOf('search')!==-1)return'Searching '+fallback;
return'Querying '+fallback;
}

function updateLastProgressStep(status){
if(aiProgressSteps.length>0){
aiProgressSteps[aiProgressSteps.length-1].status=status;
showAIProgress(aiProgressSteps);
}
}

function toggleAIWorkflowExpand(){
aiWorkflowExpanded=!aiWorkflowExpanded;
showAIProgress(aiProgressSteps);
}

function showAIProgress(steps){
var results=document.getElementById('ai-search-results');

// Deduplicate consecutive "Analyzing" steps
var displaySteps=[];
for(var i=0;i<steps.length;i++){
var step=steps[i];
if(step.label==='Analyzing'&&displaySteps.length>0&&displaySteps[displaySteps.length-1].label==='Analyzing'){
displaySteps[displaySteps.length-1].status=step.status;
}else{
displaySteps.push({label:step.label,detail:step.detail,status:step.status,type:step.type});
}
}

var totalSteps=displaySteps.length;
var completedSteps=displaySteps.filter(function(s){return s.status==='complete'}).length;
var hasActive=displaySteps.some(function(s){return s.status==='active'});
// If no steps yet, treat as "starting" (active), not "done"
var isStarting=displaySteps.length===0;
var isInProgress=hasActive||isStarting;
var showAll=aiWorkflowExpanded||totalSteps<=3;
var visibleSteps=showAll?displaySteps:displaySteps.slice(-3);
var hiddenCount=totalSteps-visibleSteps.length;

var html='<div class="ai-wf'+(isInProgress?'':' done')+'">';
html+='<div class="ai-wf-header">';
html+='<div class="ai-wf-orb'+(isInProgress?' active':' done')+'"><div class="ai-orb-core"></div><div class="ai-orb-ring"></div></div>';
html+='<span class="ai-wf-title">Progress</span>';
html+='<span class="ai-wf-count">'+(isStarting?'Starting...':(hasActive?completedSteps+'/'+totalSteps:'Done'))+'</span>';
html+='</div>';

html+='<div class="ai-wf-steps">';

if(hiddenCount>0){
html+='<div class="ai-wf-expand" onclick="toggleAIWorkflowExpand()">';
html+='<span>+'+hiddenCount+' more</span>';
html+='</div>';
}

if(displaySteps.length===0){
html+='<div class="ai-wf-step active"><div class="ai-wf-spinner"></div><div class="ai-wf-text"><span class="ai-wf-label">Starting</span></div></div>';
}else{
for(var i=0;i<visibleSteps.length;i++){
var step=visibleSteps[i];
var stepClass='ai-wf-step';
var iconHtml='';

if(step.status==='complete'){
stepClass+=' complete';
iconHtml='<svg class="ai-wf-check" viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';
}else if(step.status==='error'){
stepClass+=' error';
iconHtml='<svg class="ai-wf-error" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>';
}else{
stepClass+=' active';
iconHtml='<div class="ai-wf-spinner"></div>';
}

html+='<div class="'+stepClass+'">';
html+=iconHtml;
html+='<div class="ai-wf-text">';
html+='<span class="ai-wf-label">'+step.label+'</span>';
if(step.detail)html+='<span class="ai-wf-detail">'+step.detail+'</span>';
html+='</div></div>';
}
}

html+='</div></div>';
results.innerHTML=html;
}

var aiLoadingMessages={
slack:['Searching Slack channels...','Reading recent conversations...','Finding relevant threads...'],
jira:['Searching Jira tickets...','Checking recent issues...','Looking through projects...'],
confluence:['Searching Confluence pages...','Reading documentation...','Checking knowledge base...'],
gmail:['Searching emails...','Checking inbox...','Finding relevant messages...'],
drive:['Searching Google Drive...','Looking through documents...','Checking shared files...']
};
var aiLoadingInterval=null;

function showAILoading(sources){
// Legacy loading - now using showAIProgress instead
showAIProgress([]);
}

function stopAILoading(){
if(aiLoadingInterval){
clearInterval(aiLoadingInterval);
aiLoadingInterval=null;
}
}

function showAIResponse(response,sources){
stopAILoading();
var results=document.getElementById('ai-search-results');

// Parse sources from response
var parsed=parseAIResponseWithSources(response);
var mainContent=parsed.content;
var citedSources=parsed.sources;

var html='<div class="ai-search-response">'+
'<div class="ai-response-content" id="ai-response-content"></div>';

// Add sources section if we have any
if(citedSources.length>0){
html+='<div class="ai-sources-section">'+
'<div class="ai-sources-header">'+
'<svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg>'+
'<span>Sources</span>'+
'<span class="ai-sources-count">'+citedSources.length+'</span>'+
'</div>'+
'<div class="ai-sources-list">';

for(var i=0;i<citedSources.length;i++){
var src=citedSources[i];
var icon=getSourceIcon(src.type);
html+='<a href="'+src.url+'" target="_blank" class="ai-source-card">'+
'<span class="ai-source-num">'+src.num+'</span>'+
'<span class="ai-source-icon">'+icon+'</span>'+
'<span class="ai-source-info">'+
'<span class="ai-source-title">'+escapeHtml(src.title)+'</span>'+
'<span class="ai-source-type">'+src.type+'</span>'+
'</span>'+
'<svg class="ai-source-arrow" viewBox="0 0 24 24"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>'+
'</a>';
}

html+='</div></div>';
}

html+='<div class="ai-response-actions">'+
'<button class="ai-action-btn copy" onclick="copyAIResponse()"><svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>Copy</button>'+
'<button class="ai-action-btn" onclick="clearAISearch()"><svg viewBox="0 0 24 24"><path d="M17.65 6.35A7.96 7.96 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>New search</button>'+
'</div></div>';

results.innerHTML=html;
renderAIContent(mainContent,citedSources);
}

function parseAIResponseWithSources(response){
var sources=[];
var content=response;

// Look for ---SOURCES--- section
var sourcesMatch=response.match(/---SOURCES---\s*([\s\S]*?)\s*---END_SOURCES---/);
if(sourcesMatch){
content=response.replace(/---SOURCES---[\s\S]*---END_SOURCES---/,'').trim();
var sourcesText=sourcesMatch[1];
var lines=sourcesText.split('\n');

for(var i=0;i<lines.length;i++){
var line=lines[i].trim();
if(!line)continue;

// Parse: [1] Title | source_type | url
var match=line.match(/^\[(\d+)\]\s*([^|]+)\|\s*(\w+)\s*\|\s*(.+)$/);
if(match){
sources.push({
num:match[1],
title:match[2].trim(),
type:match[3].trim().toLowerCase(),
url:match[4].trim()
});
}
}
}

return{content:content,sources:sources};
}

function getSourceIcon(type){
var icons={
slack:'<svg viewBox="0 0 24 24"><path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zm1.271 0a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zm0 1.271a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zm10.124 2.521a2.528 2.528 0 0 1 2.52-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.52V8.834zm-1.271 0a2.528 2.528 0 0 1-2.521 2.521 2.528 2.528 0 0 1-2.521-2.521V2.522A2.528 2.528 0 0 1 15.166 0a2.528 2.528 0 0 1 2.521 2.522v6.312zm-2.521 10.124a2.528 2.528 0 0 1 2.521 2.52A2.528 2.528 0 0 1 15.166 24a2.528 2.528 0 0 1-2.521-2.522v-2.52h2.521zm0-1.271a2.528 2.528 0 0 1-2.521-2.521 2.528 2.528 0 0 1 2.521-2.521h6.312A2.528 2.528 0 0 1 24 15.166a2.528 2.528 0 0 1-2.522 2.521h-6.312z"/></svg>',
jira:'<svg viewBox="0 0 24 24"><path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.005-1.005zm5.723-5.756H5.736a5.215 5.215 0 0 0 5.215 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.758a1.001 1.001 0 0 0-1.001-1.001zM23.013 0H11.455a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A5.215 5.215 0 0 0 24 12.483V1.005A1.005 1.005 0 0 0 23.013 0z"/></svg>',
confluence:'<svg viewBox="0 0 24 24"><path d="M.87 18.257c-.248.382-.53.875-.763 1.245a.764.764 0 0 0 .255 1.04l4.965 3.054a.764.764 0 0 0 1.058-.26c.199-.332.454-.763.733-1.221 1.967-3.247 3.945-2.853 7.508-1.146l4.957 2.377a.764.764 0 0 0 1.028-.382l2.245-5.185a.764.764 0 0 0-.378-1.019c-1.24-.574-3.122-1.444-4.959-2.32-5.458-2.597-9.65-2.923-12.65 3.817zm22.26-12.514c.249-.382.531-.875.764-1.245a.764.764 0 0 0-.256-1.04L18.673.404a.764.764 0 0 0-1.058.26c-.199.332-.454.763-.733 1.221-1.967 3.247-3.945 2.853-7.508 1.146L4.417.654a.764.764 0 0 0-1.028.382L1.144 6.221a.764.764 0 0 0 .378 1.019c1.24.574 3.122 1.444 4.959 2.32 5.458 2.597 9.65 2.923 12.65-3.817z"/></svg>',
gmail:'<svg viewBox="0 0 24 24"><path d="M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 0 1 0 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L5.455 4.64 12 9.548l6.545-4.91 1.528-1.145C21.69 2.28 24 3.434 24 5.457z"/></svg>',
drive:'<svg viewBox="0 0 24 24"><path d="M12.01 1.485c-2.082 0-3.754.02-3.743.047.01.02 1.708 3.001 3.774 6.62l3.76 6.574h3.76c2.081 0 3.753-.02 3.742-.047-.005-.02-1.708-3.001-3.775-6.62l-3.76-6.574h-3.758zm-5.04 8.866l-3.758 6.574c-.02.047 1.598.067 3.68.047l3.782-.047 1.879-3.287 1.879-3.287-1.879-3.287c-1.035-1.808-1.889-3.287-1.899-3.287s-1.745 2.934-3.684 6.574zm10.045 6.621h-3.76L9.49 23.426c-.01.027 1.651.047 3.733.047h3.76l1.879-3.287 1.879-3.287-1.879-3.287c-1.035-1.808-1.889-3.287-1.899-3.287-.01 0-.009.022.037.047z"/></svg>',
github:'<svg viewBox="0 0 24 24"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>'
};
return icons[type]||'<svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg>';
}

function escapeHtml(text){
var div=document.createElement('div');
div.textContent=text;
return div.innerHTML;
}

function renderAIContent(content,sources){
var el=document.getElementById('ai-response-content');
if(!el)return;

// Format markdown and convert citation refs to links
var formatted=formatMarkdown(content);

// Convert [1], [2] etc to clickable links that scroll to source
if(sources.length>0){
for(var i=0;i<sources.length;i++){
var src=sources[i];
var regex=new RegExp('\\['+src.num+'\\]','g');
formatted=formatted.replace(regex,'<a href="'+src.url+'" target="_blank" class="ai-cite" title="'+escapeHtml(src.title)+'">['+src.num+']</a>');
}
}

el.innerHTML=formatted;
}

function formatMarkdown(text){
// Parse markdown tables first (before other transformations)
text=parseMarkdownTables(text);

// Extract fenced code blocks FIRST to protect them from other transformations
var codeBlocks=[];
text=text.replace(/```(\w*)\n([\s\S]*?)```/g,function(m,lang,code){
var idx=codeBlocks.length;
var escaped=code.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
var langLabel=lang?'<span class="code-lang">'+lang+'</span>':'';
codeBlocks.push('<div class="code-block">'+langLabel+'<pre><code>'+escaped.trimEnd()+'</code></pre></div>');
return '%%CODEBLOCK_'+idx+'%%';
});

// Numbered lists (1. 2. 3.)
text=text.replace(/^(\d+)\. (.+)$/gm,'<li value="$1">$2</li>');
text=text.replace(/(<li value="\d+">[^]*?<\/li>\n?)+/g,'<ol>$&</ol>');

text=text.replace(/^### (.+)$/gm,'<h4>$1</h4>');
text=text.replace(/^## (.+)$/gm,'<h3>$1</h3>');
text=text.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
text=text.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank">$1</a>');
text=text.replace(/`([^`]+)`/g,'<code>$1</code>');
text=text.replace(/^- (.+)$/gm,'<li>$1</li>');
text=text.replace(/(<li>[^]*?<\/li>\n?)+/g,function(m){
if(m.indexOf('value=')>-1)return m; // skip numbered lists
return '<ul>'+m+'</ul>';
});
text=text.replace(/\n\n/g,'</p><p>');
text='<p>'+text+'</p>';
text=text.replace(/<p><\/p>/g,'');
text=text.replace(/<p>(<h[34]>)/g,'$1');
text=text.replace(/(<\/h[34]>)<\/p>/g,'$1');
text=text.replace(/<p>(<ul>)/g,'$1');
text=text.replace(/(<\/ul>)<\/p>/g,'$1');
text=text.replace(/<p>(<ol>)/g,'$1');
text=text.replace(/(<\/ol>)<\/p>/g,'$1');
text=text.replace(/<p>(<table)/g,'$1');
text=text.replace(/(<\/table>)<\/p>/g,'$1');
text=text.replace(/<p>(<div class="code-block")/g,'$1');

// Restore fenced code blocks
for(var i=0;i<codeBlocks.length;i++){
text=text.replace('%%CODEBLOCK_'+i+'%%',codeBlocks[i]);
}

return text;
}

function parseMarkdownTables(text){
// Match markdown table blocks
var tableRegex=/(?:^|\n)((?:\|[^\n]+\|\n)+)/g;
return text.replace(tableRegex,function(match,tableBlock){
var lines=tableBlock.trim().split('\n').filter(function(l){return l.trim();});
if(lines.length<2)return match;
// Check if second line is separator (|---|---|)
var sepLine=lines[1];
if(!/^\|[\s\-:|]+\|$/.test(sepLine))return match;
// Parse header
var headerCells=lines[0].split('|').filter(function(c,i,arr){return i>0&&i<arr.length-1;});
// Parse body rows (skip header and separator)
var bodyRows=lines.slice(2);
var html='<table class="md-table"><thead><tr>';
headerCells.forEach(function(cell){
html+='<th>'+cell.trim()+'</th>';
});
html+='</tr></thead><tbody>';
bodyRows.forEach(function(row){
var cells=row.split('|').filter(function(c,i,arr){return i>0&&i<arr.length-1;});
html+='<tr>';
cells.forEach(function(cell){
html+='<td>'+cell.trim()+'</td>';
});
html+='</tr>';
});
html+='</tbody></table>';
return '\n'+html+'\n';
});
}

function showAIError(message,tool){
stopAILoading();
var results=document.getElementById('ai-search-results');
var actionHtml='<button class="ai-error-retry" onclick="submitAISearch()">Try again</button>';
if(tool==='gmail'||tool==='drive'){
var label=tool==='gmail'?'Connect Gmail':'Connect Drive';
actionHtml='<button class="ai-error-retry" onclick="startAISourceAuth(\''+tool+'\')">'+label+'</button>';
}
results.innerHTML='<div class="ai-search-error">'+
'<div class="ai-error-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg></div>'+
'<div class="ai-error-text">'+message+'</div>'+
actionHtml+
'</div>';
}

function startAISourceAuth(tool){
var endpoint=tool==='gmail'?'/gmail/auth':'/drive/auth';
fetch(SEARCH_SERVICE+endpoint,{method:'POST'})
.then(function(r){return r.json();})
.then(function(data){
if(data&&data.authUrl){
window.open(data.authUrl,'_blank');
}
})
.catch(function(e){console.error('Auth error:',e);});
}

function showAIEmpty(){
var results=document.getElementById('ai-search-results');
results.innerHTML='<div class="ai-search-empty">'+
'<svg class="ai-empty-lucide" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.4)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>'+
'<span>Ask anything across your connected tools</span>'+
'</div>';
}

function clearAISearch(){
var input=document.getElementById('ai-search-input');
if(input){input.value='';input.focus();}
showAIEmpty();
}

function copyAIResponse(){
var content=document.getElementById('ai-response-content');
if(!content)return;
navigator.clipboard.writeText(content.innerText).then(function(){
var btn=document.querySelector('.ai-action-btn.copy');
btn.classList.add('copied');
btn.innerHTML='<svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>Copied';
setTimeout(function(){
btn.classList.remove('copied');
btn.innerHTML='<svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>Copy';
},2000);
});
}

// Keyboard shortcuts for AI search
document.addEventListener('keydown',function(e){
// Open AI search with Cmd+/ (works from anywhere)
if(e.key==='/'&&(e.metaKey||e.ctrlKey)&&!aiSearchOpen){
e.preventDefault();
openAISearch();
}
// Close with Escape
if(e.key==='Escape'&&aiSearchOpen){
e.preventDefault();
closeAISearch();
}
// Submit with Enter
if(e.key==='Enter'&&aiSearchOpen&&document.activeElement.id==='ai-search-input'){
e.preventDefault();
submitAISearch();
}
});

// Handle AI search input events
document.addEventListener('DOMContentLoaded',function(){
var aiInput=document.getElementById('ai-search-input');
if(aiInput){
aiInput.addEventListener('keydown',function(e){
e.stopPropagation();
// Handle Enter key for submit
if(e.key==='Enter'){
e.preventDefault();
submitAISearch();
}
// Handle Escape to close
if(e.key==='Escape'){
e.preventDefault();
closeAISearch();
}
});
aiInput.addEventListener('keyup',function(e){e.stopPropagation();});
aiInput.addEventListener('keypress',function(e){e.stopPropagation();});
}
});

// Server connectivity check
var serverConnected=true;
function checkServerConnection(){
var banner=document.getElementById('server-error-banner');
if(!banner)return;
fetch(S+'/hub/status',{signal:AbortSignal.timeout(5000)})
.then(function(r){
if(r.ok){
serverConnected=true;
banner.style.display='none';
return true;
}
throw new Error('Server error');
})
.catch(function(){
serverConnected=false;
banner.style.display='flex';
});
}
function retryServerConnection(){
var btn=document.querySelector('.server-error-banner button');
if(btn)btn.textContent='Checking...';
checkServerConnection();
setTimeout(function(){
var btn=document.querySelector('.server-error-banner button');
if(btn)btn.textContent='Retry';
},2000);
}
// Check on load and periodically
setTimeout(checkServerConnection,1000);
setInterval(checkServerConnection,30000);

