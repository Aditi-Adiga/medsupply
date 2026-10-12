const base = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '');
let token = '';
let expired = () => {};
export function setSession(value: string) { token = value; }
export function onExpired(handler: () => void) { expired = handler; }
export class ApiError extends Error { constructor(public status:number, message:string) { super(message); } }
export async function api<T>(path:string, method='GET', body?:unknown, challenge?:string):Promise<T> {
  const usedToken=challenge||token;
  let response:Response;
  try {
    response = await fetch(base + path, {method, signal:AbortSignal.timeout(15000), credentials:'omit', cache:'no-store',
      headers:{'Content-Type':'application/json', ...(usedToken ? {Authorization:`Bearer ${usedToken}`} : {})},
      body: body === undefined ? undefined : JSON.stringify(body)});
  } catch { throw new ApiError(0, 'Cannot connect to the backend. Start the Python API on port 8000. If it is running, check the API address and allowed frontend origin. This error does not check your password.'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && !challenge && token && token===usedToken) { setSession(''); expired(); }
    const defaults:Record<number,string> = {401:'Sign in again. Your session has ended.',403:'You do not have permission for this action.',409:'Stock or request status changed. Refresh and try again.',422:'Check the form values.',429:'Too many attempts. Wait before trying again.'};
    throw new ApiError(response.status, typeof data.detail==='string' ? data.detail : defaults[response.status] || 'The server could not complete this request.');
  }
  return data as T;
}
