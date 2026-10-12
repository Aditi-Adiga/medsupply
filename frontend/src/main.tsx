import React from 'react';
import ReactDOM from 'react-dom/client';
import { Theme } from '@radix-ui/themes';
import '@radix-ui/themes/styles.css';
import './style.css';
import './cliniq.css';
import App from './App';
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><Theme accentColor="indigo" grayColor="slate" radius="medium"><App/></Theme></React.StrictMode>);
