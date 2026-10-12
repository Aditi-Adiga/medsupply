import Icon from './Icons';
import Home from './Home';
import { useEffect, useState, useRef, useId, cloneElement, isValidElement } from 'react';
import type { FormEvent } from 'react';
import { Button, Badge } from '@radix-ui/themes';
import { api, onExpired, setSession } from './api';
import type { User, Workspace } from './types';
import { Inventory, MedicineDetail, Supply, Requests, Alerts, Settings } from './screens';

export function ErrorNotice({message}:{message:string}) { return message ? <div role="alert" className="notice error">{message}</div> : null; }
export function Severity({value}:{value:string}) { return <Badge color={value==='CRITICAL'||value==='HIGH'?'red':value==='MEDIUM'?'amber':'teal'}>{value}</Badge>; }
export function Empty({children}:{children:React.ReactNode}) { return <div className="empty">{children}</div>; }
export function Field({label,children}:{label:string;children:React.ReactNode}) { const id=useId();return <label className="field" htmlFor={id}><span id={`${id}-label`}>{label}</span>{isValidElement(children)?cloneElement(children as React.ReactElement<{id:string;'aria-labelledby':string}>,{id,'aria-labelledby':`${id}-label`}):children}</label>; }
export function useTask() {
  const lock=useRef(false);
  const [busy,setBusy]=useState(false), [error,setError]=useState(''), [success,setSuccess]=useState('');
  async function run(work:()=>Promise<void>) { if(lock.current)return; lock.current=true;setBusy(true);setError('');setSuccess('');try{await work();}catch(e){setError(e instanceof Error?e.message:'The request failed.');}finally{lock.current=false;setBusy(false);} }
  return {busy,error,success,setSuccess,run};
}

function SignIn({complete}:{complete:(token:string,codes:string[])=>Promise<void>}) {
  const passwordId=useId();
  const [showPassword,setShowPassword]=useState(false);
  const [challenge,setChallenge]=useState(''), [setup,setSetup]=useState(false), [qr,setQr]=useState('');
  const [username,setUsername]=useState(''), [password,setPassword]=useState(''), [code,setCode]=useState(''), [recovery,setRecovery]=useState(false);
  const task=useTask();
  async function submit(event:FormEvent) { event.preventDefault();
    const secret=password;setPassword('');
    await task.run(async()=>{
      if(!challenge){
        const r=await api<{challenge:string;setup_required:boolean}>('/auth/login','POST',{username,password:secret});
        setChallenge(r.challenge);setSetup(r.setup_required);
        if(r.setup_required) setQr((await api<{qr:string}>('/auth/setup','POST',undefined,r.challenge)).qr);
      }else{
        const second=code;setCode('');
        const r=await api<{token:string;recovery_codes:string[]}>('/auth/verify','POST',{code:second,recovery},challenge);
        setQr('');setChallenge('');await complete(r.token,r.recovery_codes);
      }
    });
  }
  return <main className="signin"><section className="signin-story"><div className="brand"><span className="brand-mark">✚</span><span>MedSupply<span className="brand-sub">MEDICAL SUPPLY INTELLIGENCE</span></span></div><div className="welcome-symbol"><Icon name="inventory" size={42}/></div><p className="eyebrow">CONNECTED HOSPITAL SUPPLY</p><h1>The right supply.<br/>At the right time.</h1><p>Predict shortages. Find available stock. Keep each hospital ready to deliver care.</p><div className="signin-features"><div><Icon name="alerts"/><span>Early shortage alerts</span></div><div><Icon name="requests"/><span>Safe hospital transfers</span></div><div><Icon name="shield"/><span>Access for your hospital only</span></div></div><div className="story-note">Synthetic data · Every transfer needs approval</div></section><section className="signin-form"><div className="auth-icon"><Icon name="shield" size={30}/></div><span className="eyebrow">SECURE HOSPITAL ACCESS</span><h2>{challenge?(setup?'Set up your authenticator':'Verify your sign-in'):'Administrator sign-in'}</h2><p>Sign in to your hospital workspace. Your password and authenticator code protect access.</p><ErrorNotice message={task.error}/><form onSubmit={submit}>
    {!challenge?<><Field label="Username"><input placeholder="e.g. h01-admin" autoComplete="username" required value={username} onChange={e=>setUsername(e.target.value)}/></Field><div className="field"><label htmlFor={passwordId}>Password</label><div className="password-input"><input id={passwordId} placeholder="Enter your password" autoComplete="current-password" required type={showPassword?'text':'password'} value={password} onChange={e=>setPassword(e.target.value)}/><button type="button" aria-label={showPassword?'Hide password':'Show password'} aria-pressed={showPassword} onClick={()=>setShowPassword(!showPassword)}><Icon name="eye"/></button></div></div></>:<>
      {setup&&<div className="qr">{qr?<img src={qr} alt="Authenticator setup QR code" width="200" height="200"/>:<p role="status">Preparing authenticator setup…</p>}<p>Scan with your authenticator app. The code is a time-based one-time password (TOTP).</p></div>}
      <Field label={recovery?'Recovery code':'Authenticator code'}><input required type="password" autoComplete="one-time-code" inputMode={recovery?'text':'numeric'} value={code} onChange={e=>setCode(e.target.value)}/></Field>
      {!setup&&<label className="check"><input type="checkbox" checked={recovery} onChange={e=>setRecovery(e.target.checked)}/>Use a recovery code</label>}
    </>}
    <Button type="submit" size="3" disabled={task.busy||(setup&&!qr)}>{task.busy?'Please wait…':challenge?'Verify and sign in':'Continue'}</Button>
  </form>{challenge&&<Button variant="ghost" onClick={()=>{setChallenge('');setQr('');setCode('');setRecovery(false);}}>Start sign-in again</Button>}<div className="auth-security"><Icon name="shield" size={16}/><span>Two-factor verification · Hospital access control</span></div><p className="small">Keep your codes private. A used authenticator code cannot be reused.</p></section></main>;
}

type View='home'|'inventory'|'medicine'|'supply'|'requests'|'alerts'|'settings';
const navigation:[View,string,string][]=[['home','Hospital home','home'],['inventory','Inventory','inventory'],['supply','Supply assistant','supply'],['requests','Redistribution','requests'],['alerts','Alerts','alerts'],['settings','Account settings','settings']];
export default function App(){
  const generation=useRef(0);
  const [user,setUser]=useState<User|null>(null), [data,setData]=useState<Workspace|null>(null), [view,setView]=useState<View>('home');
  const [medicine,setMedicine]=useState(''), [requestId,setRequestId]=useState(''), [codes,setCodes]=useState<string[]>([]), [message,setMessage]=useState('');
  const task=useTask();
  function clear(){generation.current++;setSession('');setUser(null);setData(null);setCodes([]);setView('home');setRequestId('');setMedicine('');}
  useEffect(()=>{onExpired(()=>{clear();setMessage('Your session ended. Sign in again.');});return()=>onExpired(()=>{});},[]);
  useEffect(()=>{if(!user?.session_expires_at)return;const timer=setTimeout(()=>{clear();setMessage('Your session ended. Sign in again.');},Math.max(0,Date.parse(user.session_expires_at)-Date.now()));return()=>clearTimeout(timer);},[user]);
  async function complete(token:string,recovery:string[]){const current=++generation.current;setSession(token);try{const u=await api<User>('/auth/me');if(current!==generation.current)return;setUser(u);setCodes(recovery);setMessage('');}catch(e){if(current===generation.current)clear();throw e;}}
  async function refresh(){await task.run(async()=>{
    if(!user)return;
    const current=generation.current;
    const [medicines,inventory,risks,alerts,requests]=await Promise.all([api<Workspace['medicines']>('/medicines'),api<Workspace['inventory']>(`/hospitals/${encodeURIComponent(user.hospital_id)}/inventory`),api<Workspace['risks']>('/risk'),api<Workspace['alerts']>('/alerts'),api<Workspace['requests']>('/requests')]);
    if(current===generation.current)setData({medicines,inventory,risks,alerts,requests});
  });}
  useEffect(()=>{if(user)void refresh();},[user]);
  function openMedicine(id:string){setMedicine(id);setView('medicine');}
  function openRequest(id:string){setRequestId(id);setView('requests');}
  async function logout(){await task.run(async()=>{try{await api('/auth/logout','POST');}catch{setMessage('Signed out locally. The backend could not end the session. It will expire automatically.');}finally{clear();}});}
  if(!user)return <><ErrorNotice message={message}/><SignIn complete={complete}/></>;
  if(codes.length)return <main className="recovery panel"><p className="eyebrow">ACCOUNT SECURITY</p><h1>Save your recovery codes</h1><p>They are shown once. Each code works once. Keep them in a safe place.</p><div className="codes">{codes.map(code=><code key={code}>{code}</code>)}</div><Button onClick={()=>setCodes([])}>I saved the codes. Continue.</Button></main>;
  return <div className="shell"><a className="skip" href="#content">Skip to main content</a><aside className="sidebar"><div className="brand"><span className="brand-mark">✚</span><span>MedSupply<span className="brand-sub">HOSPITAL WORKSPACE</span></span></div><p className="sidebar-caption">HOSPITAL OPERATIONS</p><nav aria-label="Main navigation">{navigation.map(([key,label,number])=><button key={key} aria-label={label} aria-current={view===key||(key==='inventory'&&view==='medicine')?'page':undefined} onClick={()=>{setView(key);if(key==='requests')setRequestId('');}}><Icon name={number}/>{label}{key==='alerts'&&!!data?.alerts.filter(a=>a.state==='Active').length&&<span className="nav-count">{data.alerts.filter(a=>a.state==='Active').length}</span>}</button>)}</nav><div className="sidebar-bottom"><span className="live-dot"/> Synthetic data<br/><small>Transfer times are simulated.</small></div></aside><div className="workspace"><header className="topbar"><div><span className="eyebrow">ASSIGNED HOSPITAL · {user.hospital_id}</span><strong>{user.hospital_name}</strong></div><div className="account"><button className="alert-shortcut" aria-label="Open hospital alerts" onClick={()=>setView('alerts')}><Icon name="alerts"/>{!!data?.alerts.filter(a=>a.state==='Active').length&&<span className="notification-dot"/>}</button><span className="user-avatar">{user.username.slice(0,2).toUpperCase()}</span><span>{user.username}</span><Button variant="outline" disabled={task.busy} onClick={()=>void logout()}>Logout</Button></div></header><main id="content" tabIndex={-1}><div className="page-top"><Button variant="ghost" disabled={task.busy} onClick={()=>void refresh()}><Icon name="refresh" size={16}/>{task.busy?'Refreshing…':'Refresh data'}</Button></div><ErrorNotice message={task.error}/>
    {!data?<>{task.busy?<div role="status" className="empty">Loading your hospital workspace…</div>:<Empty>Workspace is unavailable. Use Refresh data to try again.</Empty>}</>:<>
      {view==='home'&&<Home data={data} user={user} openMedicine={openMedicine} openRequest={openRequest} findSupply={(id?:string)=>{setMedicine(id||'');setView('supply');}} openInventory={()=>setView('inventory')} openAlerts={()=>setView('alerts')}/>}
      {view==='inventory'&&<Inventory data={data} openMedicine={openMedicine}/>}
      {view==='medicine'&&<MedicineDetail id={medicine} back={()=>setView('inventory')} findSupply={(id?:string)=>{setMedicine(id||'');setView('supply');}}/>}
      {view==='supply'&&<Supply initialMedicine={medicine} data={data} refresh={refresh} openRequest={openRequest}/>}
      {view==='requests'&&<Requests data={data} user={user} selected={requestId} select={setRequestId} refresh={refresh}/>}
      {view==='alerts'&&<Alerts data={data} refresh={refresh} openMedicine={openMedicine} openRequest={openRequest}/>}
      {view==='settings'&&<Settings user={user} signedOut={clear}/>}
    </>}</main><footer>Synthetic hospital data. Review recommendations before acting.</footer></div></div>;
}
