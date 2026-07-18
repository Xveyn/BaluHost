import { SidebarBrand } from './SidebarBrand';
import { SidebarNav } from './SidebarNav';
import type { LayoutNavItem } from './layoutNavConfig';

interface DesktopSidebarProps {
  isImpersonating: boolean;
  items: LayoutNavItem[];
  adminStartIndex: number;
}

export function DesktopSidebar({ isImpersonating, items, adminStartIndex }: DesktopSidebarProps) {
  return (
    <aside className={`fixed left-0 hidden lg:flex w-72 flex-col border-r border-white/10 bg-white/5 backdrop-blur-3xl shadow-[0_8px_32px_rgba(0,0,0,0.5),inset_0_1px_0_rgba(255,255,255,0.1)] ${isImpersonating ? 'top-10 h-[calc(100vh-2.5rem)]' : 'top-0 h-screen'}`}>
      <div className="px-6 pt-10 pb-8">
        <SidebarBrand variant="desktop" />
      </div>
      <nav className="flex-1 px-4 overflow-y-auto scrollbar-thin pb-4">
        <SidebarNav items={items} adminStartIndex={adminStartIndex} variant="desktop" />
      </nav>
    </aside>
  );
}
