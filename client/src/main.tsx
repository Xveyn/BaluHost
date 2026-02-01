import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Toaster } from 'react-hot-toast'
import { ThemeProvider } from './contexts/ThemeContext'
import { initPluginSDK } from './lib/pluginSDK'
import './index.css'
import App from './App.tsx'

// Initialize Plugin SDK before app renders
// This exposes React, UI components, icons, toast, and API to plugins via window.BaluHost
initPluginSDK();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <App />
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: '#1f2937',
            color: '#f9fafb',
            border: '1px solid #374151'
          }
        }}
      />
    </ThemeProvider>
  </StrictMode>,
)
