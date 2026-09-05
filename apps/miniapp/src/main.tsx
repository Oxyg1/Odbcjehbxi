import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/inter/wght.css';
import './styles/tokens.css';
import './styles/base.css';
import './styles/editor.css';
import App from './App';
import { applySafeAreaVars, initTelegram } from './telegram/webapp';

initTelegram();
applySafeAreaVars();
window.addEventListener('resize', applySafeAreaVars);

const container = document.getElementById('root');
if (!container) throw new Error('Нет узла #root');

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
