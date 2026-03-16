import React from 'react';
import ReactDOM from 'react-dom/client';

import { App } from '@app/App';
import '@app/styles/global.css';
import '@shared/i18n/i18n';
import 'reactflow/dist/style.css';

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('Root element #root was not found.');
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
