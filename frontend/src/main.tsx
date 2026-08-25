import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './index.css';

// Optional, privacy-friendly analytics — 100% opt-in and zero-cost:
// set VITE_ANALYTICS_SRC to a self-hosted Umami/GoatCounter/Plausible
// script URL and VITE_ANALYTICS_DOMAIN to your site domain. When unset,
// NO third-party request is ever made.
const analyticsSrc = import.meta.env.VITE_ANALYTICS_SRC as string | undefined;
const analyticsDomain = import.meta.env.VITE_ANALYTICS_DOMAIN as
  string | undefined;
if (analyticsSrc) {
  const script = document.createElement('script');
  script.defer = true;
  if (analyticsDomain) {
    script.setAttribute('data-domain', analyticsDomain);
  }
  script.src = analyticsSrc;
  document.head.appendChild(script);
}

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element #root is missing from index.html');
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <BrowserRouter future={{ v7_startTransition: true,
      v7_relativeSplatPath: true }}>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
