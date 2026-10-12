import {defineConfig} from '@playwright/test';
import {randomBytes} from 'node:crypto';
process.env.MSI_E2E_PASSWORD ||= randomBytes(24).toString('hex');
export default defineConfig({testDir:'e2e',workers:1,fullyParallel:false,timeout:90000,
  use:{baseURL:'http://127.0.0.1:5173',browserName:'chromium',viewport:{width:1440,height:1000},trace:'off'},
  webServer:[{command:'python ../tests/react_demo_server.py',url:'http://127.0.0.1:8001/api/v1/health',timeout:90000,reuseExistingServer:false,env:{MSI_E2E_PASSWORD:process.env.MSI_E2E_PASSWORD!}},
  {command:'npm run dev',url:'http://127.0.0.1:5173',timeout:60000,reuseExistingServer:false,env:{VITE_API_URL:'http://127.0.0.1:8001/api/v1'}}]});
