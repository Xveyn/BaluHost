interface FanChartLegendProps {
  currentTemp: number | null;
  emergencyTemp: number;
}

export default function FanChartLegend({ currentTemp, emergencyTemp }: FanChartLegendProps) {
  return (
    <div className="mt-4 flex flex-wrap gap-4 text-xs text-slate-400">
      <div className="flex items-center gap-2">
        <div className="w-3 h-3 rounded-full bg-sky-500 border-2 border-slate-900" />
        <span>Curve Points</span>
      </div>
      {currentTemp !== null && (
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-emerald-400 border-2 border-slate-900" />
          <span>Current Operating Point</span>
        </div>
      )}
      <div className="flex items-center gap-2">
        <div className="w-8 h-0.5 bg-rose-500" style={{ borderTop: '2px dashed' }} />
        <span>Emergency Temp ({emergencyTemp}°C)</span>
      </div>
    </div>
  );
}
