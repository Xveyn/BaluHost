import { createElement } from 'react';
import {
  Lock, FileText, Terminal, Activity, Users, Share2, Database,
  RefreshCw, GitBranch, Smartphone, Link, Wifi, MonitorSmartphone,
  Network, KeyRound, Zap, Cpu, BatteryCharging, Wind, BarChart3,
  Moon, Clock, Settings, Key, Heart, Bell, Download, Server,
  Globe, Puzzle, Gauge, Cloud, Plug, ShieldBan, Layers, ArrowRightLeft,
} from 'lucide-react';
import type { ReactNode } from 'react';

export interface TagConfig {
  category: string;
  title: string;
  icon: ReactNode;
}

const icon = (Icon: React.ComponentType<{ className?: string }>) =>
  createElement(Icon, { className: 'w-5 h-5' });

export const tagMapping: Record<string, TagConfig> = {
  'auth':              { category: 'core',     title: 'Authentication',        icon: icon(Lock) },
  'files':             { category: 'core',     title: 'Files',                 icon: icon(FileText) },
  'logging':           { category: 'core',     title: 'Logging',               icon: icon(Terminal) },
  'system':            { category: 'core',     title: 'System',                icon: icon(Activity) },
  'users':             { category: 'core',     title: 'Users',                 icon: icon(Users) },
  'activity':          { category: 'core',     title: 'Activity',              icon: icon(Activity) },
  'shares':            { category: 'sharing',  title: 'Shares',                icon: icon(Share2) },
  'backups':           { category: 'sharing',  title: 'Backup',                icon: icon(Database) },
  'sync':              { category: 'sharing',  title: 'Sync',                  icon: icon(RefreshCw) },
  'vcl':               { category: 'sharing',  title: 'Version Control (VCL)', icon: icon(GitBranch) },
  'mobile':            { category: 'devices',  title: 'Mobile Devices',        icon: icon(Smartphone) },
  'desktop-pairing':   { category: 'devices',  title: 'Desktop Pairing',       icon: icon(Link) },
  'vpn':               { category: 'devices',  title: 'VPN',                   icon: icon(Wifi) },
  'devices':           { category: 'devices',  title: 'Devices',               icon: icon(MonitorSmartphone) },
  'server-profiles':   { category: 'devices',  title: 'Server Profiles',       icon: icon(Network) },
  'vpn-profiles':      { category: 'devices',  title: 'VPN Profiles',          icon: icon(KeyRound) },
  'power-management':  { category: 'system',   title: 'Power Management',      icon: icon(Zap) },
  'power-presets':     { category: 'system',   title: 'Power Presets',          icon: icon(Cpu) },
  'energy-monitoring': { category: 'system',   title: 'Energy Monitoring',     icon: icon(BatteryCharging) },
  'fan-control':       { category: 'system',   title: 'Fan Control',           icon: icon(Wind) },
  'system-monitoring': { category: 'system',   title: 'Monitoring',            icon: icon(BarChart3) },
  'sleep-mode':        { category: 'system',   title: 'Sleep Mode',            icon: icon(Moon) },
  'schedulers':        { category: 'system',   title: 'Schedulers',            icon: icon(Clock) },
  'admin':             { category: 'admin',    title: 'Admin Services',        icon: icon(Settings) },
  'monitoring':        { category: 'admin',    title: 'Metrics',               icon: icon(BarChart3) },
  'api-keys':          { category: 'admin',    title: 'API Keys',              icon: icon(Key) },
  'health':            { category: 'admin',    title: 'Health',                icon: icon(Heart) },
  'firebase':          { category: 'admin',    title: 'Firebase',              icon: icon(Bell) },
  'updates':           { category: 'features', title: 'Updates',               icon: icon(Download) },
  'samba':             { category: 'features', title: 'Samba/SMB',             icon: icon(Server) },
  'webdav':            { category: 'features', title: 'WebDAV',                icon: icon(Globe) },
  'plugins':           { category: 'features', title: 'Plugins',               icon: icon(Puzzle) },
  'notifications':     { category: 'features', title: 'Notifications',         icon: icon(Bell) },
  'benchmark':         { category: 'features', title: 'Benchmark',             icon: icon(Gauge) },
  'cloud-import':      { category: 'features', title: 'Cloud Import',          icon: icon(Cloud) },
  'power-monitoring':  { category: 'features', title: 'Smart Devices',          icon: icon(Plug) },
  'pihole':            { category: 'features', title: 'Pi-hole DNS',           icon: icon(ShieldBan) },
  'ssd-cache':         { category: 'features', title: 'SSD File Cache',        icon: icon(Layers) },
  'ssd-migration':     { category: 'features', title: 'Migration',             icon: icon(ArrowRightLeft) },
};

export const categoryLabels: Record<string, string> = {
  core: 'Core',
  sharing: 'Sharing',
  devices: 'Devices',
  system: 'System',
  admin: 'Admin',
  features: 'Features',
  other: 'Other',
};

export const categoryOrder = ['core', 'sharing', 'devices', 'system', 'admin', 'features', 'other'];
