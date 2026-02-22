import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  useReactFlow,
  type Edge,
  type EdgeProps,
} from '@xyflow/react';
import { useEffect, useRef, useState } from 'react';

import type { ApiEdge } from '../types';

export function BreakpointEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  data,
}: EdgeProps) {
  const { setEdges } = useReactFlow();
  const [hovered, setHovered] = useState(false);
  const hideTimerRef = useRef<number | null>(null);
  const breakpoint = Boolean((data as ApiEdge['data'])?.breakpoint);
  const horizontalOffset = targetX >= sourceX ? 16 : -16;
  const verticalOffset = -10;

  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const toggleBreakpoint = () => {
    setEdges((edges) =>
      edges.map((edge: Edge) => {
        if (edge.id !== id) {
          return edge;
        }

        const nextBreakpoint = !Boolean(edge.data?.breakpoint);
        const condition = edge.data?.condition;
        const inactiveStyle =
          condition === 'true'
            ? { stroke: '#2f9e44', strokeWidth: 2 }
            : condition === 'false'
              ? { stroke: '#c92a2a', strokeWidth: 2 }
              : { stroke: '#44556f', strokeWidth: 1.5 };
        return {
          ...edge,
          data: {
            ...edge.data,
            breakpoint: nextBreakpoint,
          },
          style: {
            ...edge.style,
            ...(nextBreakpoint ? { stroke: '#d43f3a', strokeWidth: 2.4 } : inactiveStyle),
          },
        };
      }),
    );
  };

  const showControl = () => {
    if (hideTimerRef.current !== null) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    setHovered(true);
  };

  const hideControlWithDelay = () => {
    if (hideTimerRef.current !== null) {
      window.clearTimeout(hideTimerRef.current);
    }
    hideTimerRef.current = window.setTimeout(() => {
      setHovered(false);
      hideTimerRef.current = null;
    }, 350);
  };

  useEffect(() => {
    return () => {
      if (hideTimerRef.current !== null) {
        window.clearTimeout(hideTimerRef.current);
      }
    };
  }, []);

  return (
    <>
      <BaseEdge path={path} markerEnd={markerEnd} style={style} />
      <path
        d={path}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        onMouseEnter={showControl}
        onMouseLeave={hideControlWithDelay}
      />
      <EdgeLabelRenderer>
        {hovered || breakpoint ? (
          <button
            className={`edge-debug-dot ${breakpoint ? 'active' : ''}`}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX + horizontalOffset}px,${labelY + verticalOffset}px)`,
            }}
            onClick={toggleBreakpoint}
            onMouseEnter={showControl}
            onMouseLeave={hideControlWithDelay}
            title={breakpoint ? 'Disable breakpoint' : 'Enable breakpoint'}
            type="button"
          />
        ) : null}
      </EdgeLabelRenderer>
    </>
  );
}
