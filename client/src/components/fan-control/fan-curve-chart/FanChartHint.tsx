interface FanChartHintProps {
  pointCount: number;
  minPoints: number;
  maxPoints: number;
}

export default function FanChartHint({ pointCount, minPoints, maxPoints }: FanChartHintProps) {
  return (
    <p className="mt-3 text-xs text-slate-400 italic">
      <strong>Left-click</strong> on graph to add point • <strong>Drag</strong> points to move • <strong>Right-click</strong> point to remove
      {pointCount <= minPoints && ' (min 2 points)'}
      {pointCount >= maxPoints && ` (max ${maxPoints} points)`}
    </p>
  );
}
