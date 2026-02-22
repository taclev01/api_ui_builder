import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Tag } from 'antd';

import type { FlowNodeData } from '../types';

const colorByType: Record<string, string> = {
  start_python: 'green',
  start_request: 'geekblue',
  end: 'red',
  if: 'gold',
  define_variable: 'blue',
  for_each_parallel: 'cyan',
  join: 'purple',
  form_request: 'geekblue',
  paginate_request: 'blue',
  python_request: 'magenta',
  invoke_workflow: 'processing',
  auth: 'orange',
  parameters: 'gold',
  save: 'lime',
  delay: 'default',
  raise_error: 'volcano',
};

export function FlowNode({ data, selected }: NodeProps) {
  const typedData = data as FlowNodeData;
  const isAuthNode = typedData.nodeType === 'auth';
  const isParametersNode = typedData.nodeType === 'parameters';
  const isDataNode = isAuthNode || isParametersNode;
  const isIfNode = typedData.nodeType === 'if';
  const isStartNode = typedData.nodeType === 'start_python' || typedData.nodeType === 'start_request';
  const isTerminalNode = typedData.nodeType === 'end' || typedData.nodeType === 'raise_error';

  return (
    <div className={`flow-node ${selected ? 'is-selected' : ''} ${isDataNode ? 'is-auth-node' : ''}`}>
      {!isDataNode && !isStartNode ? <Handle type="target" position={Position.Top} /> : null}
      <div className="flow-node-title">{typedData.label}</div>
      <Tag color={colorByType[typedData.nodeType] ?? 'default'}>{typedData.nodeType}</Tag>
      {isDataNode || isTerminalNode ? null : isIfNode ? (
        <>
          <div className="if-handle-label if-handle-label-true">TRUE</div>
          <Handle id="true" type="source" position={Position.Bottom} style={{ left: '28%' }} />
          <div className="if-handle-label if-handle-label-false">FALSE</div>
          <Handle id="false" type="source" position={Position.Bottom} style={{ left: '72%' }} />
        </>
      ) : (
        <Handle type="source" position={Position.Bottom} />
      )}
    </div>
  );
}
