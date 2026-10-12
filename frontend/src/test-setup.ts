import '@testing-library/jest-dom/vitest';
import {afterEach,vi} from 'vitest';
import {cleanup} from '@testing-library/react';
import {setSession} from './api';
afterEach(()=>{cleanup();setSession('');vi.restoreAllMocks();});
class ResizeObserverMock { observe(){} unobserve(){} disconnect(){} }
globalThis.ResizeObserver=ResizeObserverMock;
window.matchMedia=vi.fn().mockImplementation(()=>({matches:false,addListener(){},removeListener(){},addEventListener(){},removeEventListener(){},dispatchEvent(){return false;}}));
