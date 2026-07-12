import type { TFunction } from 'i18next';
import type { FanCurvePoint } from '../../api/fan-control';

export interface CurveBounds {
  minPwm: number;
  maxPwm: number;
}

/**
 * Validates a fan curve. Pure — pwm bounds and the i18n `t` function are passed in.
 * Rules (unchanged from FanDetails): >= 2 points, strictly ascending temps,
 * every pwm within [minPwm, maxPwm].
 */
export function validateCurvePoints(
  points: FanCurvePoint[],
  bounds: CurveBounds,
  t: TFunction,
): { valid: boolean; error?: string } {
  if (points.length < 2) {
    return { valid: false, error: t('system:fanControl.validation.minPoints') };
  }

  const sorted = [...points].sort((a, b) => a.temp - b.temp);
  for (let i = 0; i < sorted.length - 1; i++) {
    if (sorted[i].temp >= sorted[i + 1].temp) {
      return { valid: false, error: t('system:fanControl.validation.ascendingTemp') };
    }
  }

  for (const point of points) {
    if (point.pwm < bounds.minPwm || point.pwm > bounds.maxPwm) {
      return {
        valid: false,
        error: t('system:fanControl.validation.pwmRange', { min: bounds.minPwm, max: bounds.maxPwm }),
      };
    }
  }

  return { valid: true };
}
