import {test,expect,type Page} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {mkdirSync} from 'node:fs';
function helper(...args:string[]){return execFileSync('python',['../tests/react_demo_server.py',...args],{encoding:'utf8'}).trim();}
async function signIn(page:Page,hospital:string){
  await page.goto('/');await page.getByLabel('Username').fill('test-'+hospital);await page.getByLabel('Password',{exact:true}).fill(process.env.MSI_E2E_PASSWORD!);await page.getByRole('button',{name:'Continue',exact:true}).click();
  await expect(page.getByAltText('Authenticator setup QR code')).toBeVisible();await expect(page.getByRole('navigation')).toHaveCount(0);
  await page.getByLabel('Authenticator code',{exact:true}).fill(helper('code',hospital));
  const response=page.waitForResponse(r=>r.url().endsWith('/auth/verify')&&r.status()===200);
  await page.getByRole('button',{name:'Verify and sign in'}).click();const token=(await (await response).json()).token as string;
  await expect(page.getByRole('heading',{name:'Save your recovery codes'})).toBeVisible();await page.getByRole('button',{name:'I saved the codes. Continue.'}).click();await expect(page.getByRole('heading',{name:'Keep care supplied.'})).toBeVisible();return token;
}
test('H01 and H02 complete a safe transfer across real React and FastAPI',async({page,browser})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  mkdirSync('../.verification/screenshots',{recursive:true});
  await page.goto('/');await page.screenshot({path:'../.verification/screenshots/react-signin-desktop.png',fullPage:true});
  const token=await signIn(page,'H01');await page.screenshot({path:'../.verification/screenshots/react-home-desktop.png',fullPage:true});
  expect((await page.request.get('http://127.0.0.1:8001/api/v1/hospitals/H02/inventory',{headers:{Authorization:`Bearer ${token}`}})).status()).toBe(403);
  expect((await page.request.post('http://127.0.0.1:8001/api/v1/requests',{headers:{Authorization:`Bearer ${token}`},data:{donor:'H03',recipient:'H02',medicine_id:'M01',quantity:1,reason:'Forbidden'}})).status()).toBe(403);
  await page.getByRole('button',{name:'Find supply'}).click();await page.getByLabel('Medicine',{exact:true}).selectOption('M01');await page.getByRole('button',{name:'Search safe stock'}).click();await page.getByRole('button',{name:'Select source'}).click();await page.getByLabel('Requested quantity').fill('100');await page.getByLabel('Reason',{exact:true}).fill('Synthetic browser integration test');
  const created=page.waitForResponse(r=>r.url().endsWith('/requests')&&r.request().method()==='POST');await page.getByRole('button',{name:'Submit supply request'}).click();const request=(await (await created).json());
  await expect(page.getByRole('heading',{name:'Requests and transfers'})).toBeVisible();expect((await page.request.post(`http://127.0.0.1:8001/api/v1/requests/${request.id}/action`,{headers:{Authorization:`Bearer ${token}`},data:{status:'Approved'}})).status()).toBe(403);
  const context=await browser.newContext();const donor=await context.newPage();await signIn(donor,'H02');await donor.getByRole('button',{name:'Requests & transfers'}).click();await donor.getByRole('button',{name:'Review',exact:true}).click();await donor.getByRole('button',{name:'Approve request',exact:true}).click();await donor.getByRole('button',{name:'Confirm action'}).click();await expect(donor.getByRole('button',{name:'Record dispatch',exact:true})).toBeVisible();expect(JSON.parse(helper('stock')).reserved).toBe(100);
  await donor.getByRole('button',{name:'Record dispatch',exact:true}).click();await donor.getByRole('button',{name:'Confirm action'}).click();await expect(donor.getByRole('heading',{name:'Paracetamol · Dispatched'})).toBeVisible();expect(JSON.parse(helper('stock'))).toEqual({quantity:900,reserved:0});
  await page.getByRole('button',{name:'Refresh data'}).click();await page.getByRole('button',{name:'Record receipt',exact:true}).click();await page.getByRole('button',{name:'Confirm action'}).click();await expect(page.getByRole('heading',{name:'Paracetamol · Received'})).toBeVisible();
  await page.getByRole('button',{name:'Inventory'}).click();await page.getByLabel('Search medicines').fill('Paracetamol');await page.getByRole('button',{name:'Inspect',exact:true}).click();await expect(page.getByRole('heading',{name:'Future demand forecast'})).toBeVisible();await expect(page.locator('.recharts-line-curve')).toHaveCount(2,{timeout:20000});await page.screenshot({path:'../.verification/screenshots/react-medicine-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:'../.verification/screenshots/react-medicine-mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.getByRole('button',{name:'Alerts'}).click();await page.getByLabel('Alert state').selectOption('all');await page.screenshot({path:'../.verification/screenshots/react-alerts-mobile.png',fullPage:true});
  await page.keyboard.press('Tab');expect(await page.evaluate(()=>document.activeElement?.tagName)).not.toBe('BODY');
  await page.getByRole('button',{name:'Inventory',exact:true}).focus();await page.keyboard.press('Enter');await expect(page.getByRole('heading',{name:'Hospital inventory'})).toBeVisible();
  await page.getByRole('button',{name:'Logout',exact:true}).click();await expect(page.getByRole('heading',{name:'Administrator sign-in'})).toBeVisible();expect(errors).toEqual([]);await context.close();
});
