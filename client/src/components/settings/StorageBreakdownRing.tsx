import { formatBytes } from '../../lib/formatters';
import type { StorageDeviceEntry } from '../../api/system';

const COLORS: Record<string, string[]> = {
  hdd: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'],
  ssd: ['#a78bfa', '#c084fc', '#818cf8', '#7c3aed', '#6366f1', '#a855f7'],
  nvme: ['#f59e0b', '#fbbf24', '#f97316', '#d97706', '#ea580c', '#eab308'],
};

function getSegmentColor(diskType: string, index: number): string {
  const palette = COLORS[diskType] || COLORS.hdd;
  return palette[index % palette.length];
}

interface StorageBreakdownRingProps {
  entries: StorageDeviceEntry[];
  totalCapacity: number;
  totalUsePercent: number;
  size?: number;
  strokeWidth?: number;
}

export default function StorageBreakdownRing({
  entries,
  totalCapacity,
  totalUsePercent,
  size = 140,
  strokeWidth = 12,
}: StorageBreakdownRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  // Build segments — each segment's angular size is proportional to its
  // capacity relative to total.  Within each segment we draw two arcs:
  // a faint background (full segment) and a saturated foreground (used %).
  let offsetAngle = 0;
  const segments = entries.map((entry, i) => {
    const proportion = totalCapacity > 0 ? entry.capacity_bytes / totalCapacity : 0;
    const segLen = proportion * circumference;
    const usedFraction = entry.capacity_bytes > 0
      ? Math.min(entry.used_bytes / entry.capacity_bytes, 1)
      : 0;
    const usedLen = usedFraction * segLen;
    const gapSize = entries.length > 1 ? 3 : 0;
    const effectiveSegLen = Math.max(segLen - gapSize, 0);
    const effectiveUsedLen = Math.min(usedLen, effectiveSegLen);

    const color = getSegmentColor(entry.disk_type, i);
    const dashBg = `${effectiveSegLen} ${circumference - effectiveSegLen}`;
    const dashFg = `${effectiveUsedLen} ${circumference - effectiveUsedLen}`;
    const offset = -(offsetAngle + gapSize / 2);

    offsetAngle += segLen;

    return { entry, color, dashBg, dashFg, offset, i };
  });

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Ring */}
      <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="transform -rotate-90">
          {/* Background track */}
          <circle
            cx={size / 2} cy={size / 2} r={radius}
            fill="none" stroke="currentColor" strokeWidth={strokeWidth}
            className="text-slate-800/40"
          />
          {segments.map(({ color, dashBg, dashFg, offset, i }) => (
            <g key={i}>
              {/* Segment background (capacity proportion, faint) */}
              <circle
                cx={size / 2} cy={size / 2} r={radius}
                fill="none" stroke={color} strokeWidth={strokeWidth}
                strokeDasharray={dashBg} strokeDashoffset={offset}
                opacity={0.25}
              />
              {/* Segment foreground (used portion, saturated) */}
              <circle
                cx={size / 2} cy={size / 2} r={radius}
                fill="none" stroke={color} strokeWidth={strokeWidth}
                strokeLinecap="butt"
                strokeDasharray={dashFg} strokeDashoffset={offset}
                className="transition-all duration-1000 ease-out"
              />
            </g>
          ))}
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xl font-bold">{totalUsePercent.toFixed(0)}%</span>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap justify-center gap-x-4 gap-y-1.5">
        {segments.map(({ entry, color, i }) => (
          <div key={i} className="flex items-center gap-1.5 text-xs text-slate-300">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: color }}
            />
            <span className="font-medium">{entry.name}</span>
            <span className="text-slate-500">{formatBytes(entry.capacity_bytes)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
