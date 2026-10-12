import type { CSSProperties } from 'react';

const paths: Record<string, string> = {
  home: 'M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z',
  inventory: 'M3 7 12 3l9 4v10l-9 4-9-4ZM3 7l9 4 9-4M12 11v10M7.5 5l9 4',
  supply: 'M10.5 18a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15ZM16 16l5 5M7 10.5h7M10.5 7v7',
  requests: 'M3 7h17l-4-4M21 17H4l4 4M20 7l-4 4M4 17l4-4',
  alerts: 'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4',
  settings: 'M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z',
  shield: 'M12 3 3 7v6c0 5 9 9 9 9s9-4 9-9V7ZM8 12l3 3 5-6',
  arrow: 'M4 12h16M14 6l6 6-6 6',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3 2',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7ZM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  refresh: 'M20 7a9 9 0 0 0-15-1L2 9M2 3v6h6M4 17a9 9 0 0 0 15 1l3-3M22 21v-6h-6',
};
export default function Icon({name,size=20,style}:{name:string;size?:number;style?:CSSProperties}) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" style={style}><path d={paths[name]||paths.home}/></svg>;
}
