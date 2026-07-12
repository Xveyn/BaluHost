import { useState, useRef, useCallback, useEffect } from 'react';
import type { MouseEvent as ReactMouseEvent, TouchEvent as ReactTouchEvent, RefObject } from 'react';
import type { FanCurvePoint } from '../api/fan-control';
import { computeChartValue, computeDraggedPoint, findNearestPointIndex } from '../components/fan-control/fanCurveGeometry';

export interface ChartDataPoint extends FanCurvePoint {
  isCurrentPoint?: boolean;
  originalIndex?: number;
}

export interface FanCurveInteractionConfig {
  minPWM: number;
  maxPWM: number;
  emergencyTemp: number;
  isReadOnly: boolean;
  minPoints: number;
  maxPoints: number;
}

export function useFanCurveInteraction(
  points: FanCurvePoint[],
  onPointsChange: (points: FanCurvePoint[]) => void,
  cfg: FanCurveInteractionConfig,
) {
  const { minPWM, maxPWM, emergencyTemp, isReadOnly, minPoints, maxPoints } = cfg;

  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);
  const [localPoints, setLocalPoints] = useState<FanCurvePoint[]>(points);
  const chartRef = useRef<HTMLDivElement>(null);
  const localPointsRef = useRef<FanCurvePoint[]>(localPoints);
  const wasDraggingRef = useRef(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  // Editing is always enabled when not read-only (FanControl-style behavior)
  const canEdit = !isReadOnly;

  // Refs for stable access in document-level handlers (survive React re-renders)
  const canEditRef = useRef(canEdit);
  const maxPointsRef = useRef(maxPoints);
  const onPointsChangeRef = useRef(onPointsChange);

  useEffect(() => { canEditRef.current = canEdit; }, [canEdit]);
  useEffect(() => { maxPointsRef.current = maxPoints; }, [maxPoints]);
  useEffect(() => { onPointsChangeRef.current = onPointsChange; }, [onPointsChange]);

  // Update local points when external points change (but not while dragging)
  useEffect(() => {
    if (draggingIndex === null) {
      setLocalPoints(points);
    }
  }, [points, draggingIndex]);

  // Keep ref in sync with state
  useEffect(() => {
    localPointsRef.current = localPoints;
  }, [localPoints]);

  const pointsWithIndices = localPoints.map((point, index) => ({
    ...point,
    originalIndex: index,
  }));

  const sortedPoints = [...pointsWithIndices].sort((a, b) => a.temp - b.temp);

  const chartData: ChartDataPoint[] = sortedPoints.map((point) => ({
    ...point,
    isCurrentPoint: false,
  }));

  const handleRemovePoint = useCallback((index: number) => {
    if (!canEdit || localPoints.length <= minPoints) return;

    const originalIndex = sortedPoints[index]?.originalIndex;
    if (originalIndex === undefined) return;

    const updatedPoints = localPoints.filter((_, i) => i !== originalIndex);
    setLocalPoints(updatedPoints);
    onPointsChange(updatedPoints);
  }, [canEdit, localPoints, minPoints, onPointsChange, sortedPoints]);

  const updatePointPosition = useCallback((clientX: number, clientY: number, index: number) => {
    if (!chartRef.current) return;

    const cartesianGrid = chartRef.current.querySelector('.recharts-cartesian-grid');
    if (!cartesianGrid) return;

    const rect = cartesianGrid.getBoundingClientRect();

    const originalIndex = sortedPoints[index].originalIndex;
    if (originalIndex === undefined) return;

    const { temp, pwm } = computeDraggedPoint(clientX, clientY, rect, { emergencyTemp, minPWM, maxPWM });

    const updatedPoints = [...localPoints];
    updatedPoints[originalIndex] = { temp, pwm };

    setLocalPoints(updatedPoints);
  }, [sortedPoints, localPoints, minPWM, maxPWM, emergencyTemp]);

  const getChartBounds = useCallback((): DOMRect | null => {
    if (!chartRef.current) return null;

    const cartesianGrid = chartRef.current.querySelector('.recharts-cartesian-grid');
    if (cartesianGrid) {
      const rect = cartesianGrid.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) return rect;
    }

    const horizontalLines = chartRef.current.querySelector('.recharts-cartesian-grid-horizontal');
    if (horizontalLines) {
      const rect = horizontalLines.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) return rect;
    }

    const surface = chartRef.current.querySelector('.recharts-surface');
    if (surface) {
      const svgRect = surface.getBoundingClientRect();
      const margin = { top: 5, right: 20, left: 0, bottom: 55 };
      const yAxis = chartRef.current.querySelector('.recharts-yAxis');
      const yAxisWidth = yAxis ? yAxis.getBoundingClientRect().width : 60;
      return new DOMRect(
        svgRect.left + margin.left + yAxisWidth,
        svgRect.top + margin.top,
        svgRect.width - margin.left - margin.right - yAxisWidth,
        svgRect.height - margin.top - margin.bottom,
      );
    }

    return null;
  }, []);

  const pixelToValue = useCallback((clientX: number, clientY: number) => {
    const bounds = getChartBounds();
    if (!bounds) return null;
    return computeChartValue(clientX, clientY, bounds, { emergencyTemp, minPWM, maxPWM });
  }, [emergencyTemp, minPWM, maxPWM, getChartBounds]);

  const findPointNear = useCallback((clientX: number, clientY: number): number | null => {
    const bounds = getChartBounds();
    if (!bounds) return null;
    return findNearestPointIndex(clientX, clientY, bounds, sortedPoints, emergencyTemp);
  }, [sortedPoints, emergencyTemp, getChartBounds]);

  const handleOverlayMouseDown = useCallback((e: ReactMouseEvent) => {
    if (!canEdit) return;

    const pointIndex = findPointNear(e.clientX, e.clientY);
    if (pointIndex === null) return; // Click-to-add handled by onClick

    e.preventDefault();
    setDraggingIndex(pointIndex);

    const handleMouseMove = (moveEvent: MouseEvent) => {
      updatePointPosition(moveEvent.clientX, moveEvent.clientY, pointIndex);
    };

    const handleMouseUp = () => {
      wasDraggingRef.current = true; // Suppress the following onClick
      setDraggingIndex(null);
      onPointsChangeRef.current(localPointsRef.current);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      requestAnimationFrame(() => { wasDraggingRef.current = false; });
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [canEdit, findPointNear, updatePointPosition]);

  const handleOverlayClick = useCallback((e: ReactMouseEvent) => {
    if (wasDraggingRef.current) {
      wasDraggingRef.current = false;
      return;
    }
    if (!canEdit) return;
    if (localPoints.length >= maxPoints) return;

    const pointIndex = findPointNear(e.clientX, e.clientY);
    if (pointIndex !== null) return;

    const values = pixelToValue(e.clientX, e.clientY);
    if (!values || !values.inBounds) return;

    const newPoint: FanCurvePoint = { temp: values.temp, pwm: values.pwm };
    const updatedPoints = [...localPoints, newPoint];
    setLocalPoints(updatedPoints);
    onPointsChange(updatedPoints);
  }, [canEdit, localPoints, maxPoints, findPointNear, pixelToValue, onPointsChange]);

  const handleOverlayContextMenu = useCallback((e: ReactMouseEvent) => {
    e.preventDefault();
    if (!canEdit) return;

    const pointIndex = findPointNear(e.clientX, e.clientY);
    if (pointIndex !== null) {
      handleRemovePoint(pointIndex);
    }
  }, [canEdit, findPointNear, handleRemovePoint]);

  const handleOverlayTouchStart = useCallback((e: ReactTouchEvent) => {
    if (!canEdit) return;

    const touch = e.touches[0];
    const pointIndex = findPointNear(touch.clientX, touch.clientY);

    if (pointIndex !== null) {
      e.preventDefault();
      setDraggingIndex(pointIndex);

      const handleTouchMove = (moveEvent: TouchEvent) => {
        const moveTouch = moveEvent.touches[0];
        updatePointPosition(moveTouch.clientX, moveTouch.clientY, pointIndex);
      };

      const handleTouchEnd = () => {
        setDraggingIndex(null);
        onPointsChangeRef.current(localPointsRef.current);
        document.removeEventListener('touchmove', handleTouchMove);
        document.removeEventListener('touchend', handleTouchEnd);
      };

      document.addEventListener('touchmove', handleTouchMove);
      document.addEventListener('touchend', handleTouchEnd);
    } else {
      const startX = touch.clientX;
      const startY = touch.clientY;

      const handleTouchEnd = (endEvent: TouchEvent) => {
        const endTouch = endEvent.changedTouches[0];
        if (!endTouch) return;

        const dist = Math.sqrt(
          Math.pow(endTouch.clientX - startX, 2) + Math.pow(endTouch.clientY - startY, 2),
        );

        if (dist >= 10) return;
        if (!canEditRef.current) return;
        if (localPointsRef.current.length >= maxPointsRef.current) return;

        const values = pixelToValue(endTouch.clientX, endTouch.clientY);
        if (!values || !values.inBounds) return;

        const newPoint: FanCurvePoint = { temp: values.temp, pwm: values.pwm };
        const updatedPoints = [...localPointsRef.current, newPoint];
        setLocalPoints(updatedPoints);
        onPointsChangeRef.current(updatedPoints);
      };

      document.addEventListener('touchend', handleTouchEnd, { once: true });
    }
  }, [canEdit, findPointNear, updatePointPosition, pixelToValue]);

  return {
    chartRef: chartRef as RefObject<HTMLDivElement>,
    overlayRef: overlayRef as RefObject<HTMLDivElement>,
    draggingIndex,
    canEdit,
    localPoints,
    sortedPoints,
    chartData,
    handleRemovePoint,
    handleOverlayMouseDown,
    handleOverlayClick,
    handleOverlayContextMenu,
    handleOverlayTouchStart,
  };
}
