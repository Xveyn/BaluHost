import { Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import Layout from '../Layout';
import { LoadingFallback } from '../ui/LoadingFallback';

// Innerer Suspense: beim Lazy-Load eines Seiten-Chunks bleibt die Sidebar stehen.
export function AppLayout() {
  return (
    <Layout>
      <Suspense fallback={<LoadingFallback />}>
        <Outlet />
      </Suspense>
    </Layout>
  );
}
