import { StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import { Toaster } from 'react-hot-toast'
import { ThemeProvider } from './contexts/ThemeContext'
import { queryClient } from './lib/queryClient'
import { persistOptions } from './lib/queryPersister'
import './i18n' // Initialize i18n before app renders
import './index.css'
import App from './App.tsx'

// Loading fallback for i18n
const I18nLoadingFallback = () => (
  <div className="flex items-center justify-center h-screen bg-slate-950">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500"></div>
  </div>
)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
      <Suspense fallback={<I18nLoadingFallback />}>
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
      </Suspense>
    </PersistQueryClientProvider>
  </StrictMode>,
)
