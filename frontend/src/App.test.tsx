import {beforeEach,describe,expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@radix-ui/themes';
import App from './App';
import {api,setSession,onExpired,ApiError} from './api';
import {permittedActions} from './screens';
import type {SupplyRequest} from './types';

const account={id:'user1',username:'h01-admin',hospital_id:'H01',hospital_name:'Demo hospital H01',role:'hospital_admin',two_factor_ready:true,external_notifications_enabled:false,session_expires_at:new Date(Date.now()+3600000).toISOString()};
const batch={batch_id:'DEMO-H01-M01',medicine_id:'M01',unit:'unit',quantity:0,reserved:0,expiry:'2027-01-01'};
const risk={key:'stock:H01:M01',kind:'Stock exhausted',severity:'CRITICAL',active:true,medicine_id:'M01',usable_quantity:0,unit:'unit',message:'M01: 0 usable units.',recommended_action:'Find a safe supply source.',stockout_in_days:0};
const alert={id:'stock:H01:M01',kind:'Stock exhausted',severity:'CRITICAL',message:'H01 stock exhausted.',state:'Active',medicine_id:'M01',request_id:null,recommended_action:'Find a safe supply source.'};
const request:SupplyRequest={id:'test-request',recipient:'H01',donor:'H02',medicine_id:'M01',unit:'unit',requested:100,approved:0,allocations:[],urgency:'Routine',reason:'Demo need',status:'Requested',in_transit:0,created:'2026-10-09T10:00:00',updated:'2026-10-09T10:00:00',created_by:'user1',history:[{action:'Requested',user_id:'user1',at:'2026-10-09T10:00:00'}]};
let extra:Record<string,unknown>;
let fetchMock:ReturnType<typeof vi.fn>;
beforeEach(()=>{
  extra={};
  fetchMock=vi.fn(async(url:string,options:RequestInit={})=>{
    const path=new URL(url).pathname.replace('/api/v1','');
    const values:Record<string,unknown>={'/auth/login':{challenge:'test-challenge',setup_required:false},'/auth/verify':{token:'verified-test-session',recovery_codes:[]},'/auth/me':account,'/medicines':[{id:'M01',name:'Paracetamol'}],'/hospitals/H01/inventory':[batch],'/risk':[risk],'/alerts':[alert],'/requests':[], '/requests/test-request':request,'/auth/logout':{message:'Signed out.'}};
    const value=path in extra?extra[path]:values[path];
    if(value instanceof Error)throw value;
    return new Response(JSON.stringify(value??{}),{status:200,headers:{'Content-Type':'application/json'}});
  });
  vi.stubGlobal('fetch',fetchMock);
});
function mount(){render(<Theme><App/></Theme>);return userEvent.setup();}
async function signIn(user:ReturnType<typeof userEvent.setup>){await user.type(screen.getByLabelText('Username'),'h01-admin');await user.type(screen.getByLabelText('Password'),'test-password-only');await user.click(screen.getByRole('button',{name:'Continue'}));await user.type(await screen.findByLabelText('Authenticator code'),'123456');await user.click(screen.getByRole('button',{name:'Verify and sign in'}));await screen.findByRole('heading',{name:'Keep care supplied.'});}

describe('Hospital interface',()=>{
  it('does not fetch protected data before the second factor',async()=>{
    const user=mount();await user.type(screen.getByLabelText('Username'),'h01-admin');await user.type(screen.getByLabelText('Password'),'test-password-only');await user.click(screen.getByRole('button',{name:'Continue'}));await screen.findByLabelText('Authenticator code');
    expect(fetchMock.mock.calls.map(c=>c[0])).toHaveLength(1);
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('Authenticator code'),'123456');await user.click(screen.getByRole('button',{name:'Verify and sign in'}));await screen.findByRole('heading',{name:'Keep care supplied.'});
    expect(fetchMock.mock.calls.some(c=>c[0].includes('/hospitals/H01/inventory'))).toBe(true);
    expect(fetchMock.mock.calls.some(c=>c[0].includes('/hospitals/H02/inventory'))).toBe(false);
    expect(localStorage.length).toBe(0);
  });
  it('shows setup QR, verifies it, and shows recovery codes once',async()=>{
    extra['/auth/login']={challenge:'setup-challenge',setup_required:true};extra['/auth/setup']={qr:'data:image/png;base64,test'};extra['/auth/verify']={token:'verified-test-session',recovery_codes:['recovery-test-code']};
    const user=mount();await user.type(screen.getByLabelText('Username'),'h01-admin');await user.type(screen.getByLabelText('Password'),'test-password-only');await user.click(screen.getByRole('button',{name:'Continue'}));expect(await screen.findByAltText('Authenticator setup QR code')).toBeInTheDocument();expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('Authenticator code'),'123456');await user.click(screen.getByRole('button',{name:'Verify and sign in'}));await screen.findByText('recovery-test-code');await user.click(screen.getByRole('button',{name:'I saved the codes. Continue.'}));await screen.findByRole('heading',{name:'Keep care supplied.'});expect(screen.queryByText('recovery-test-code')).not.toBeInTheDocument();
  });
  it('shows supply results and submits only a selected source',async()=>{
    extra['/supply/search']={message:'Select a source.',recommendations:[{donor_hospital:'H02',medicine:'M01',available_quantity:100,unit:'unit',estimated_arrival_days:1,travel_time_simulated:false,donor_city:'Udupi',recipient_city:'Mangaluru',road_distance_km:60,estimated_delivery_minutes:95,earliest_expiry:'2027-01-01',reason:'Safe stock covers donor demand.'}]};
    const user=mount();await signIn(user);await user.click(screen.getByRole('button',{name:'Supply assistant'}));await user.click(screen.getByRole('button',{name:'Search safe stock'}));await screen.findByText('Safe stock covers donor demand.');expect(screen.getByText('Udupi')).toBeInTheDocument();expect(screen.getByText('60.00 km')).toBeInTheDocument();expect(screen.getByText('1 hr 35 min')).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(c=>c[0].endsWith('/requests')&&(c[1] as RequestInit).method==='POST')).toHaveLength(0);
    await user.click(screen.getByRole('button',{name:'Select source'}));await user.type(screen.getByLabelText('Reason'),'Need safe units');
    fetchMock.mockImplementationOnce(async()=>new Response(JSON.stringify(request),{status:200}));
    await user.click(screen.getByRole('button',{name:'Submit supply request'}));
    await waitFor(()=>expect(fetchMock.mock.calls.some(c=>c[0].endsWith('/requests')&&(c[1] as RequestInit).method==='POST')).toBe(true));
    const call=fetchMock.mock.calls.find(c=>c[0].endsWith('/requests')&&(c[1] as RequestInit).method==='POST')!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({donor:'H02',medicine_id:'M01',quantity:100,urgency:'Routine',reason:'Need safe units'});
  });
  it('shows an empty supply result without invented donors',async()=>{
    extra['/supply/search']={recommendations:[],message:'No safe transfer is available.'};const user=mount();await signIn(user);await user.click(screen.getByRole('button',{name:'Supply assistant'}));await user.click(screen.getByRole('button',{name:'Search safe stock'}));await screen.findByText('No safe transfer is available for this request.');expect(screen.queryByRole('button',{name:'Select source'})).not.toBeInTheDocument();
  });
  it('shows hospital alerts and acknowledges through the backend',async()=>{
    const user=mount();await signIn(user);await user.click(screen.getByRole('button',{name:'Alerts'}));await screen.findByText('H01 stock exhausted.');await user.click(screen.getByRole('button',{name:'Acknowledge'}));await waitFor(()=>expect(fetchMock.mock.calls.some(c=>c[0].includes('/alerts/stock%3AH01%3AM01/acknowledge'))).toBe(true));
  });
  it('supports recovery-code sign-in',async()=>{
    const user=mount();await user.type(screen.getByLabelText('Username'),'h01-admin');await user.type(screen.getByLabelText('Password'),'test-password-only');await user.click(screen.getByRole('button',{name:'Continue'}));await user.click(await screen.findByLabelText('Use a recovery code'));await user.type(screen.getByLabelText('Recovery code'),'test-recovery');await user.click(screen.getByRole('button',{name:'Verify and sign in'}));await screen.findByRole('heading',{name:'Keep care supplied.'});
    const call=fetchMock.mock.calls.find(c=>c[0].endsWith('/auth/verify'))!;expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({code:'test-recovery',recovery:true});
  });
  it('shows a connection error and keeps protected data hidden',async()=>{
    extra['/auth/login']=new Error('offline');const user=mount();await user.type(screen.getByLabelText('Username'),'h01-admin');await user.type(screen.getByLabelText('Password'),'test-password-only');await user.click(screen.getByRole('button',{name:'Continue'}));await screen.findByRole('alert');expect(screen.getByRole('alert')).toHaveTextContent('Cannot connect to the backend');expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });
  it('renders a loading state while hospital data is pending',async()=>{
    const original=fetchMock.getMockImplementation() as (url:string,options:RequestInit)=>Promise<Response>;
    fetchMock.mockImplementation(async(url:string,options:RequestInit)=>url.endsWith('/risk')?new Promise(()=>{}):original(url,options));
    const user=mount();await signInWithoutHome(user);expect(await screen.findByRole('status')).toHaveTextContent('Loading your hospital workspace');
  });
  it('clears protected data after session expiry',async()=>{
    const user=mount();await signIn(user);fetchMock.mockResolvedValue(new Response(JSON.stringify({detail:'Sign in again.'}),{status:401}));await user.click(screen.getByRole('button',{name:'Refresh data'}));await screen.findByRole('heading',{name:'Administrator sign-in'});expect(screen.queryByRole('navigation')).not.toBeInTheDocument();expect(screen.queryByText('H01 stock exhausted.')).not.toBeInTheDocument();
  });
  it('restricts actions by participant and transfer state',()=>{
    expect(permittedActions(request,'H01')).toEqual(['Cancelled']);expect(permittedActions(request,'H02')).toEqual(['Approved','Rejected','Cancelled']);expect(permittedActions(request,'H03')).toEqual([]);expect(permittedActions({...request,status:'Dispatched'},'H01')).toEqual(['Received']);expect(permittedActions({...request,status:'Received'},'H01')).toEqual([]);
  });
  it('ends an idle session at the expiry time given by the backend',async()=>{
    extra['/auth/me']={...account,session_expires_at:new Date(Date.now()+2500).toISOString()};
    const user=mount();await signIn(user);await screen.findByRole('heading',{name:'Administrator sign-in'},{timeout:4000});expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });
});
async function signInWithoutHome(user:ReturnType<typeof userEvent.setup>){await user.type(screen.getByLabelText('Username'),'h01-admin');await user.type(screen.getByLabelText('Password'),'test-password-only');await user.click(screen.getByRole('button',{name:'Continue'}));await user.type(await screen.findByLabelText('Authenticator code'),'123456');await user.click(screen.getByRole('button',{name:'Verify and sign in'}));}
it('returns clear permission and reservation conflict errors',async()=>{
  setSession('test');fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({detail:'Safe stock is insufficient.'}),{status:409}));await expect(api('/requests/test/action','POST',{})).rejects.toEqual(new ApiError(409,'Safe stock is insufficient.'));
  fetchMock.mockResolvedValueOnce(new Response('{}',{status:403}));await expect(api('/hospitals/H02/inventory')).rejects.toMatchObject({status:403});
});
it('does not expire a new session when an old request returns late',async()=>{
  let finish!:(response:Response)=>void;
  fetchMock.mockImplementationOnce(()=>new Promise<Response>(resolve=>{finish=resolve;}));
  const expired=vi.fn();onExpired(expired);setSession('old-test-session');
  const request=api('/risk');setSession('new-test-session');finish(new Response('{}',{status:401}));
  await expect(request).rejects.toMatchObject({status:401});expect(expired).not.toHaveBeenCalled();
  await api('/auth/me');expect((fetchMock.mock.calls.at(-1)![1] as RequestInit).headers).toMatchObject({Authorization:'Bearer new-test-session'});onExpired(()=>{});
});
