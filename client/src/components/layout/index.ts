// Only re-export what Layout.tsx actually imports through this barrel.
// Everything else in layout/ (SidebarBrand, SidebarNav, layoutNavConfig's
// buildNavItems/navIcon/pluginNavIcon/PI_NAV_PATHS/LayoutNavItem) is consumed
// via direct sibling/file-path imports (DesktopSidebar/MobileSidebar import
// SidebarBrand/SidebarNav directly; useLayoutNav.ts imports layoutNavConfig
// directly) — re-exporting them here would be dead surface (#301).
export { DesktopSidebar } from './DesktopSidebar';
export { MobileSidebar } from './MobileSidebar';
export { LayoutHeader } from './LayoutHeader';
export { PendingPowerOverlay } from './PendingPowerOverlay';
