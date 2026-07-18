import { Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import Layout from '../Layout';
import { LoadingFallback } from '../ui/LoadingFallback';

// Mounted once by a single pathless parent route (see App.tsx), with all page
// routes as children rendered through <Outlet/>. That makes Layout persistence
// a structural property of the route tree, not an accident of every route
// happening to reference the same Layout import (the old per-route
// `<Route element={<Layout>...</Layout>}>` pattern relied on the latter and was
// fragile to change). The Suspense boundary lives *inside* Layout, wrapping only
// Outlet, so a slow page-chunk load shows the fallback in the content area only —
// the sidebar/header stay mounted and visible instead of blanking too.
export function AppLayout() {
  return (
    <Layout>
      <Suspense fallback={<LoadingFallback size="inline" />}>
        <Outlet />
      </Suspense>
    </Layout>
  );
}
