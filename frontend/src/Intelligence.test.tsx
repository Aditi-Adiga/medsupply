import {beforeEach,it,expect,vi} from 'vitest';
import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Theme} from '@radix-ui/themes';
import Intelligence from './Intelligence';
import type {IntelligenceSummary} from './types';

const summary:IntelligenceSummary={hospital_id:'H01',generated_at:'2026-10-09T03:00:00Z',method:'Local rules.',summary_lines:['1 medicine is out of stock.'],counts:{out_of_stock:1},priority_count:2,priorities:[{id:'stock1',medicine_id:'M07',title:'Insulin',message:'Stock is empty.',severity:'CRITICAL',target:'supply',button:'Find supply'},{id:'request1',request_id:'request1',title:'Paracetamol',message:'Request needs approval.',severity:'HIGH',target:'request',button:'Review request'}],surge_rule:'Test rule.',trends:[{medicine_id:'M07',medicine_name:'Insulin',unit:'unit',status:'historical',reason:'Historical synthetic demand.',baseline_average:10,recent_average:20,increase_percent:100,surge:true,current_surge:false,points:[{date:'2025-12-30',quantity:10},{date:'2025-12-31',quantity:20}]}]};
beforeEach(()=>vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify(summary),{status:200}))));
it('shows historical dates without claiming a current surge and opens selected actions',async()=>{
  const medicine=vi.fn(),request=vi.fn(),supply=vi.fn();const user=userEvent.setup();
  render(<Theme><Intelligence hospital="H01" refreshKey={1} openMedicine={medicine} openRequest={request} findSupply={supply}/></Theme>);
  await screen.findByText('1 medicine is out of stock.');expect(screen.getByText('Historical data')).toBeInTheDocument();expect(screen.queryByText('Current demand surge')).not.toBeInTheDocument();
  expect(screen.getByRole('img')).toHaveAccessibleName('Insulin demand from 2025-12-30 to 2025-12-31');
  await user.click(screen.getByRole('button',{name:'Find supply'}));expect(supply).toHaveBeenCalledWith('M07');
  await user.click(screen.getByRole('button',{name:'Review request'}));expect(request).toHaveBeenCalledWith('request1');
  await user.click(screen.getByRole('button',{name:'Open demand details'}));expect(medicine).toHaveBeenCalledWith('M07');
});
it('rejects a summary for another hospital',async()=>{
  render(<Theme><Intelligence hospital="H02" refreshKey={1} openMedicine={vi.fn()} openRequest={vi.fn()} findSupply={vi.fn()}/></Theme>);
  expect(await screen.findByRole('alert')).toHaveTextContent('backend summary is unavailable');
  expect(screen.queryByText('1 medicine is out of stock.')).not.toBeInTheDocument();
});
