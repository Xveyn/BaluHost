/**
 * PropertyBadge -- displays a colored badge for a power property level.
 */

import type { ServicePowerProperty } from '../../api/power-management';
import { PROPERTY_INFO } from '../../api/power-management';
import { getPropertyColorClasses } from './utils';

interface PropertyBadgeProps {
  property: ServicePowerProperty;
  size?: 'sm' | 'md' | 'lg';
}

export function PropertyBadge({ property, size = 'md' }: PropertyBadgeProps) {
  const info = PROPERTY_INFO[property];
  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
    lg: 'px-4 py-2 text-base',
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${getPropertyColorClasses(property)} ${sizeClasses[size]}`}
    >
      <span>{info.icon}</span>
      <span>{info.name}</span>
    </span>
  );
}
