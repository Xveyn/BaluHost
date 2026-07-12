export interface ChartValueConfig {
  emergencyTemp: number;
  minPWM: number;
  maxPWM: number;
}

export interface RectLike {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * Click / tap-to-add path (from pixelToValue): INTEGER rounding + inBounds flag.
 */
export function computeChartValue(
  clientX: number,
  clientY: number,
  bounds: RectLike,
  cfg: ChartValueConfig,
): { temp: number; pwm: number; inBounds: boolean } {
  const x = clientX - bounds.left;
  const y = clientY - bounds.top;
  const tempRange = cfg.emergencyTemp + 10;

  const temp = Math.round((x / bounds.width) * tempRange);
  const pwm = Math.round(100 - (y / bounds.height) * 100);

  return {
    temp: Math.max(0, Math.min(cfg.emergencyTemp + 10, temp)),
    pwm: Math.max(cfg.minPWM, Math.min(cfg.maxPWM, pwm)),
    inBounds: x >= -5 && x <= bounds.width + 5 && y >= -5 && y <= bounds.height + 5,
  };
}

/**
 * Drag path (from updatePointPosition): 0.1 rounding, clamped.
 */
export function computeDraggedPoint(
  clientX: number,
  clientY: number,
  plotRect: RectLike,
  cfg: ChartValueConfig,
): { temp: number; pwm: number } {
  const x = clientX - plotRect.left;
  const y = clientY - plotRect.top;
  const chartWidth = plotRect.width;
  const chartHeight = plotRect.height;

  const tempRange = cfg.emergencyTemp + 10;
  const pwmRange = 100;

  const newTemp = Math.round(((x / chartWidth) * tempRange) * 10) / 10;
  const newPWM = Math.round((100 - (y / chartHeight) * pwmRange) * 10) / 10;

  return {
    temp: Math.max(0, Math.min(cfg.emergencyTemp + 10, newTemp)),
    pwm: Math.max(cfg.minPWM, Math.min(cfg.maxPWM, newPWM)),
  };
}

/**
 * Nearest curve point (in sorted order) within hitRadius, or null (from findPointNear).
 */
export function findNearestPointIndex(
  clientX: number,
  clientY: number,
  bounds: RectLike,
  sortedPoints: { temp: number; pwm: number }[],
  emergencyTemp: number,
  hitRadius = 10,
): number | null {
  const x = clientX - bounds.left;
  const y = clientY - bounds.top;
  const tempRange = emergencyTemp + 10;

  let nearestIndex: number | null = null;
  let nearestDist = Infinity;

  sortedPoints.forEach((point, index) => {
    const pointX = (point.temp / tempRange) * bounds.width;
    const pointY = ((100 - point.pwm) / 100) * bounds.height;
    const dist = Math.sqrt(Math.pow(x - pointX, 2) + Math.pow(y - pointY, 2));

    if (dist < hitRadius && dist < nearestDist) {
      nearestDist = dist;
      nearestIndex = index;
    }
  });

  return nearestIndex;
}
