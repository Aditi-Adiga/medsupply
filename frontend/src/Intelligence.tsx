import {useEffect,useState} from 'react';
import {Button} from '@radix-ui/themes';
import {api} from './api';
import {Severity} from './App';
import type {IntelligenceSummary,Trend,Priority} from './types';

function MiniTrend({trend}:{trend:Trend}){
  if(!trend.points.length)return <p>Not enough demand data.</p>;
  const max=Math.max(1,...trend.points.map(p=>p.quantity),trend.baseline_average||0);
  const y=(q:number)=>100-q/max*80;
  const points=trend.points.map((p,i)=>`${10+i*280/Math.max(1,trend.points.length-1)},${y(p.quantity)}`).join(' ');
  return <><svg viewBox="0 0 300 115" role="img" aria-label={`${trend.medicine_name} demand from ${trend.points[0].date} to ${trend.points.at(-1)!.date}`} style={{width:'100%',height:120}}>
    {trend.baseline_average!=null&&<line x1="10" x2="290" y1={y(trend.baseline_average)} y2={y(trend.baseline_average)} stroke="#9ca3af" strokeDasharray="5 4"/>}
    <polyline points={points} fill="none" stroke="#6655c5" strokeWidth="3"/>
  </svg><p className="small">{trend.points[0].date} to {trend.points.at(-1)!.date}. Dashed line: previous 14-day average. Demand in {trend.unit}/day.</p></>;
}

export default function Intelligence({hospital,refreshKey,openMedicine,openRequest,findSupply}:{hospital:string;refreshKey:unknown;openMedicine:(id:string)=>void;openRequest:(id:string)=>void;findSupply:(id?:string)=>void}){
  const [value,setValue]=useState<IntelligenceSummary|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0),[medicine,setMedicine]=useState('');
  useEffect(()=>{let active=true;setError('');setValue(null);api<IntelligenceSummary>('/intelligence/summary').then(result=>{
    if(!Array.isArray(result.summary_lines)||!Array.isArray(result.trends)||result.hospital_id!==hospital)throw new Error('The backend summary is unavailable. Restart the updated backend.');
    if(active){setValue(result);setMedicine(old=>result.trends.some(t=>t.medicine_id===old)?old:result.trends[0]?.medicine_id||'');}
  }).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[hospital,refreshKey,retry]);
  function act(item:Priority){if(item.target==='request'&&item.request_id)openRequest(item.request_id);else if(item.target==='supply'&&item.medicine_id)findSupply(item.medicine_id);else if(item.medicine_id)openMedicine(item.medicine_id);}
  const trend=value?.trends.find(t=>t.medicine_id===medicine);
  return <section className="panel" aria-label="Hospital intelligence"><div className="section-title"><h2>Hospital assistant summary</h2><span className="small">Your hospital only</span></div>
    {error?<><p role="alert">{error}</p><Button variant="outline" onClick={()=>setRetry(retry+1)}>Retry summary</Button></>:!value?<p role="status">Checking stock, requests and demand history…</p>:<>
      <ul>{value.summary_lines.map(line=><li key={line}>{line}</li>)}</ul><p className="small">{value.method} Updated {new Date(value.generated_at).toLocaleString()}.</p>
      <h3>Next actions</h3>{value.priorities.length?value.priorities.map(item=><article className="risk-row" key={item.id}><div><Severity value={item.severity}/><h3>{item.title}</h3><p>{item.message}</p></div><Button variant="outline" onClick={()=>act(item)}>{item.button}</Button></article>):<p>No priority action was detected in the available hospital data.</p>}
      {value.priority_count>3&&<p className="small">Showing the top 3 of {value.priority_count} actions. More details are available below.</p>}
      <h3>Demand trend</h3>{value.trends.length?<><label className="field"><span>Trend medicine</span><select value={medicine} onChange={e=>setMedicine(e.target.value)}>{value.trends.map(t=><option key={t.medicine_id} value={t.medicine_id}>{t.medicine_name}{t.current_surge?' · Demand surge':''}</option>)}</select></label>
        {trend&&<><p><strong>{trend.status==='historical'?'Historical data':trend.status==='insufficient'?'Not enough data':trend.current_surge?'Current demand surge':'No surge detected'}</strong> · {trend.reason}</p><MiniTrend trend={trend}/>
          {trend.baseline_average!=null&&<p>Previous 14-day average: {trend.baseline_average}. Latest 3-day average: {trend.recent_average} {trend.unit}/day.{trend.increase_percent!=null?` Change: ${trend.increase_percent}%.`:' Percentage change is unavailable because baseline demand is zero.'}{trend.status==='historical'&&trend.surge?' The historical records meet the surge rule. This is not a current alert.':''}</p>}
          <Button variant="outline" onClick={()=>openMedicine(trend.medicine_id)}>Open demand details</Button>
          <details><summary>Trend values and rule</summary><p>{value.surge_rule}</p><div className="table-wrap"><table><thead><tr><th>Date</th><th>Demand ({trend.unit})</th></tr></thead><tbody>{trend.points.map((p,i)=><tr key={p.date+':'+i}><td>{p.date}</td><td>{p.quantity}</td></tr>)}</tbody></table></div></details>
        </>}</>:<p>Demand history is unavailable for this hospital.</p>}
    </>}
  </section>;
}
