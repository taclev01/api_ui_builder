import type { Edge, Node } from '@xyflow/react';

export type ApiNodeType =
  | 'start'
  | 'end'
  | 'if'
  | 'define_variable'
  | 'for_each_parallel'
  | 'join'
  | 'form_request'
  | 'python_request'
  | 'invoke_workflow'
  | 'auth'
  | 'save'
  | 'delay'
  | 'raise_error';

export type FlowNodeData = {
  label: string;
  nodeType: ApiNodeType;
  config: Record<string, unknown>;
};

export type FlowEdgeData = {
  breakpoint?: boolean;
  condition?: 'true' | 'false';
};

export type ApiNode = Node<FlowNodeData, 'apiNode'>;
export type ApiEdge = Edge<FlowEdgeData, 'breakpoint'>;

export type NodeTemplate = {
  type: ApiNodeType;
  label: string;
  defaultConfig: Record<string, unknown>;
};
