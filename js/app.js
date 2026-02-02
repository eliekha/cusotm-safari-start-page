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
var defaultHubSources={jira:true,confluence:true,slack:true,gmail:true,drive:true,aiBrief:true};
if(s){try{var p=JSON.parse(s);if(!p.theme)p.theme='dark';if(p.hubEnabled===undefined)p.hubEnabled=true;if(!p.hubSources)p.hubSources=defaultHubSources;return p;}catch(e){}}
return {name:'',links:defaultLinks,bg:gradients[0].value,theme:'dark',logo:'',calEnabled:false,calUrl:'',calMinutes:60,hubEnabled:true,hubSources:defaultHubSources};
}
function saveToStorage(settings){localStorage.setItem('startpage',JSON.stringify(settings));}

var settings=getSettings();
var g=document.getElementById('g'),t=document.getElementById('t'),d=document.getElementById('d'),s=document.getElementById('s'),r=document.getElementById('r'),ql=document.getElementById('ql'),S='http://127.0.0.1:18765',D,I=-1,W=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'],M=['January','February','March','April','May','June','July','August','September','October','November','December'];

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
if(data.error){container.classList.remove('show');return;}
container.classList.add('show');
var events=data.events||[];
var inMeeting=data.in_meeting;
var currentMeeting=data.current_meeting;
if(inMeeting&&currentMeeting){
inCallEl.style.display='flex';
document.getElementById('cal-current-title').textContent=currentMeeting.title;
document.getElementById('cal-upcoming-count').textContent=events.length>0?events.length+' upcoming':'';
eventsEl.classList.toggle('collapsed',!calendarExpanded);
}else{
inCallEl.style.display='none';
eventsEl.classList.remove('collapsed');
calendarExpanded=false;
inCallEl.classList.remove('expanded');
}
if(events.length===0&&!inMeeting){eventsEl.innerHTML='<div class="cal-empty">No upcoming meetings</div>';return;}
if(events.length===0){eventsEl.innerHTML='';return;}
var html='';
events.forEach(function(evt){
var mins=evt.minutes_until;
var countdownClass='cal-countdown';
var countdownText='';
if(mins<=0){countdownText='Now';countdownClass='cal-countdown now';}
else if(mins<=5){countdownText='In '+mins+' min';countdownClass='cal-countdown soon';}
else if(mins<60){countdownText='In '+mins+' min';}
else{var hrs=Math.floor(mins/60);var m=mins%60;countdownText='In '+hrs+'h'+(m>0?' '+m+'m':'');}
var joinHtml=evt.meet_link?'<a href="'+evt.meet_link+'" class="cal-join" target="_blank"><svg viewBox="0 0 24 24"><path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/></svg>Join</a>':'';
html+='<div class="cal-card"><div class="cal-card-inner">';
html+='<div class="cal-icon"><svg viewBox="0 0 24 24"><path d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2zm-7 5h5v5h-5v-5z"/></svg></div>';
html+='<div class="cal-info"><div class="cal-title">'+evt.title+'</div>';
html+='<div class="cal-meta"><span class="cal-time">'+evt.start_formatted+'</span><span class="'+countdownClass+'">'+countdownText+'</span></div></div>';
html+=joinHtml+'</div></div>';
});
eventsEl.innerHTML=html;
}
function fetchCalendar(){
if(!settings.calEnabled){return;}
var container=document.getElementById('cal-container');
var eventsEl=document.getElementById('cal-events');
// Show cached data immediately, or loading indicator
if(calendarCache){
renderCalendarData(calendarCache);
}else{
container.classList.add('show');
eventsEl.innerHTML='<div class="cal-loading"><div class="cal-spinner"></div><span class="cal-loading-text">Loading calendar...</span></div>';
}
var url=S+'/calendar?minutes='+(settings.calMinutes||180)+'&limit=3';
fetch(url,{signal:AbortSignal.timeout(10000)})
.then(function(r){return r.json();})
.then(function(data){
calendarCache=data;
try{localStorage.setItem('calCache',JSON.stringify(data));}catch(e){}
renderCalendarData(data);
})
.catch(function(e){
console.log('Calendar error:',e);
document.getElementById('cal-container').classList.remove('show');
});
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
toggleHubSettings();
fetchHubAuthStatus();
}
function fetchHubAuthStatus(){
fetch(S+'/hub/status',{signal:AbortSignal.timeout(5000)})
.then(function(r){return r.json();})
.then(function(status){
var atlassian=status.atlassian||{};
var slack=status.slack||{};
var gmail=status.gmail||{};
var needsSetup=[];
updateSourceStatus('hub-jira-status',atlassian.authenticated,atlassian.configured);
updateSourceStatus('hub-confluence-status',atlassian.authenticated,atlassian.configured);
if(!atlassian.authenticated&&atlassian.configured)needsSetup.push('atlassian');
else if(!atlassian.configured)needsSetup.push('atlassian-config');
updateSourceStatus('hub-slack-status',slack.authenticated,slack.configured);
if(!slack.authenticated&&slack.configured)needsSetup.push('slack');
else if(!slack.configured)needsSetup.push('slack-config');
updateSourceStatus('hub-gmail-status',gmail.authenticated,gmail.configured);
if(!gmail.authenticated)needsSetup.push('gmail');
showSetupHints(needsSetup);
})
.catch(function(){
['hub-jira-status','hub-confluence-status','hub-slack-status','hub-gmail-status'].forEach(function(id){
var el=document.getElementById(id);
if(el){el.textContent='Unknown';el.className='hub-source-status warning';}
});
});
}
function updateSourceStatus(id,authenticated,configured){
var el=document.getElementById(id);
if(!el)return;
if(authenticated){
el.textContent='Connected';
el.className='hub-source-status connected';
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
html+='<br><strong>Gmail:</strong> Add gmail MCP to <code>.devsai.json</code> and run <code>mcp-gmail auth</code> to authenticate with Google.';
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

