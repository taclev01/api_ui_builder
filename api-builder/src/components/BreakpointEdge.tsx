import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  useReactFlow,
  type EdgeProps,
} from '@xyflow/react';

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
  const breakpoint = Boolean((data as ApiEdge['data'])?.breakpoint);

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
      edges.map((edge) => {
        if (edge.id !== id) {
          return edge;
        }

        const nextBreakpoint = !Boolean(edge.data?.breakpoint);
        return {
          ...edge,
          data: {
            ...edge.data,
            breakpoint: nextBreakpoint,
          },
          style: {
            ...edge.style,
            stroke: nextBreakpoint ? '#d43f3a' : '#44556f',
            strokeWidth: nextBreakpoint ? 2.4 : 1.5,
          },
        };
      }),
    );
  };

  return (
    <>
      <BaseEdge path={path} markerEnd={markerEnd} style={style} />
      <EdgeLabelRenderer>
        <button
          className={`edge-breakpoint-btn ${breakpoint ? 'active' : ''}`}
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
          }}
          onClick={toggleBreakpoint}
          title={breakpoint ? 'Disable breakpoint' : 'Enable breakpoint'}
          type="button"
        >
          STOP
        </button>
      </EdgeLabelRenderer>
    </>
  );
}
