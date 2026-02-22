import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type EdgeChange,
  type NodeChange,
} from '@xyflow/react';
import {
  Button,
  Card,
  Divider,
  Drawer,
  Form,
  Input,
  InputNumber,
  Layout,
  List,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd';

import { BreakpointEdge } from './components/BreakpointEdge';
import { CodeEditor } from './components/CodeEditor';
import { FlowNode } from './components/FlowNode';
import { NODE_TEMPLATES } from './nodeTemplates';
import type { ApiEdge, ApiNode, NodeTemplate } from './types';

import '@xyflow/react/dist/style.css';
import './App.css';

const { Header, Content, Sider } = Layout;

type NodeFormValues = {
  label?: string;
  ifExpression?: string;
  defineName?: string;
  defineSource?: string;
  defineSelector?: string;
  defineDefault?: string;
  forListExpr?: string;
  forItemName?: string;
  forMaxConcurrency?: number;
  joinMergeStrategy?: string;
  requestMethod?: string;
  requestUrl?: string;
  requestAuthRef?: string;
  requestTimeoutMs?: number;
  requestRetryAttempts?: number;
  requestBackoff?: string;
  requestCircuitThreshold?: number;
  requestCircuitOpenMs?: number;
  pythonFunctionName?: string;
  pythonAuthRef?: string;
  invokeTargetWorkflowId?: string;
  invokeTargetWorkflowVersionId?: string;
  invokePublishedOnly?: boolean;
  invokeInputMode?: string;
  invokeInputSource?: string;
  authType?: string;
  authTokenVar?: string;
  authHeaderName?: string;
  saveKey?: string;
  saveFrom?: string;
  delayMs?: number;
  raiseErrorMessage?: string;
};

const initialNodes: ApiNode[] = [
  {
    id: 'n-1',
    type: 'apiNode',
    position: { x: 140, y: 120 },
    data: { label: 'Start', nodeType: 'start', config: {} },
  },
  {
    id: 'n-2',
    type: 'apiNode',
    position: { x: 140, y: 280 },
    data: {
      label: 'Form Request',
      nodeType: 'form_request',
      config: {
        method: 'GET',
        url: 'https://api.example.com/resource',
        timeoutMs: 10000,
        retryAttempts: 3,
        backoff: 'exponential',
        circuitFailureThreshold: 5,
        circuitOpenMs: 30000,
      },
    },
  },
  {
    id: 'n-3',
    type: 'apiNode',
    position: { x: 140, y: 440 },
    data: { label: 'End', nodeType: 'end', config: {} },
  },
];

const initialEdges: ApiEdge[] = [
  {
    id: 'e-1-2',
    source: 'n-1',
    target: 'n-2',
    type: 'breakpoint',
    data: { breakpoint: false },
    style: { stroke: '#44556f', strokeWidth: 1.5 },
  },
  {
    id: 'e-2-3',
    source: 'n-2',
    target: 'n-3',
    type: 'breakpoint',
    data: { breakpoint: false },
    style: { stroke: '#44556f', strokeWidth: 1.5 },
  },
];

function createNodeFromTemplate(template: NodeTemplate, id: string, index: number): ApiNode {
  return {
    id,
    type: 'apiNode',
    position: {
      x: 120 + (index % 3) * 220,
      y: 120 + Math.floor(index / 3) * 160,
    },
    data: {
      label: template.label,
      nodeType: template.type,
      config: structuredClone(template.defaultConfig),
    },
  };
}

function toStringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function toNumberValue(value: unknown, fallback: number): number {
  return typeof value === 'number' ? value : fallback;
}

function toBoolValue(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function configToFormValues(node: ApiNode): NodeFormValues {
  const config = node.data.config;

  const baseValues: NodeFormValues = {
    label: node.data.label,
  };

  switch (node.data.nodeType) {
    case 'if':
      return {
        ...baseValues,
        ifExpression: toStringValue(config.expression, 'vars.status == "ok"'),
      };
    case 'define_variable':
      return {
        ...baseValues,
        defineName: toStringValue(config.name, 'new_var'),
        defineSource: toStringValue(config.source, 'last_response'),
        defineSelector: toStringValue(config.selector, 'body.data.id'),
        defineDefault: toStringValue(config.defaultValue),
      };
    case 'for_each_parallel':
      return {
        ...baseValues,
        forListExpr: toStringValue(config.listExpr, 'vars.items'),
        forItemName: toStringValue(config.itemName, 'item'),
        forMaxConcurrency: toNumberValue(config.maxConcurrency, 5),
      };
    case 'join':
      return {
        ...baseValues,
        joinMergeStrategy: toStringValue(config.mergeStrategy, 'collect_list'),
      };
    case 'form_request':
      return {
        ...baseValues,
        requestMethod: toStringValue(config.method, 'GET'),
        requestUrl: toStringValue(config.url, 'https://api.example.com/resource'),
        requestAuthRef: toStringValue(config.authRef),
        requestTimeoutMs: toNumberValue(config.timeoutMs, 10000),
        requestRetryAttempts: toNumberValue(config.retryAttempts, 3),
        requestBackoff: toStringValue(config.backoff, 'exponential'),
        requestCircuitThreshold: toNumberValue(config.circuitFailureThreshold, 5),
        requestCircuitOpenMs: toNumberValue(config.circuitOpenMs, 30000),
      };
    case 'python_request':
      return {
        ...baseValues,
        pythonFunctionName: toStringValue(config.functionName, 'custom_request'),
        pythonAuthRef: toStringValue(config.authRef),
        requestTimeoutMs: toNumberValue(config.timeoutMs, 10000),
        requestRetryAttempts: toNumberValue(config.retryAttempts, 3),
        requestBackoff: toStringValue(config.backoff, 'exponential'),
      };
    case 'invoke_workflow':
      return {
        ...baseValues,
        invokeTargetWorkflowId: toStringValue(config.targetWorkflowId),
        invokeTargetWorkflowVersionId: toStringValue(config.targetWorkflowVersionId),
        invokePublishedOnly: toBoolValue(config.publishedOnly, true),
        invokeInputMode: toStringValue(config.inputMode, 'inherit'),
        invokeInputSource: toStringValue(config.inputSource, 'vars.input'),
      };
    case 'auth':
      return {
        ...baseValues,
        authType: toStringValue(config.authType, 'bearer'),
        authTokenVar: toStringValue(config.tokenVar, 'vars.token'),
        authHeaderName: toStringValue(config.headerName, 'Authorization'),
      };
    case 'save':
      return {
        ...baseValues,
        saveKey: toStringValue(config.key, 'result'),
        saveFrom: toStringValue(config.from, 'nodes.form_request.output'),
      };
    case 'delay':
      return {
        ...baseValues,
        delayMs: toNumberValue(config.ms, 250),
      };
    case 'raise_error':
      return {
        ...baseValues,
        raiseErrorMessage: toStringValue(config.message, 'Failed validation.'),
      };
    default:
      return baseValues;
  }
}

function buildConfigFromValues(
  node: ApiNode,
  values: NodeFormValues,
  pythonCode: string,
): Record<string, unknown> {
  switch (node.data.nodeType) {
    case 'if':
      return {
        expression: values.ifExpression ?? 'vars.status == "ok"',
      };
    case 'define_variable':
      return {
        name: values.defineName ?? 'new_var',
        source: values.defineSource ?? 'last_response',
        selector: values.defineSelector ?? 'body.data.id',
        defaultValue: values.defineDefault ?? '',
      };
    case 'for_each_parallel':
      return {
        listExpr: values.forListExpr ?? 'vars.items',
        itemName: values.forItemName ?? 'item',
        maxConcurrency: values.forMaxConcurrency ?? 5,
      };
    case 'join':
      return {
        mergeStrategy: values.joinMergeStrategy ?? 'collect_list',
      };
    case 'form_request':
      return {
        method: values.requestMethod ?? 'GET',
        url: values.requestUrl ?? '',
        authRef: values.requestAuthRef ?? '',
        timeoutMs: values.requestTimeoutMs ?? 10000,
        retryAttempts: values.requestRetryAttempts ?? 3,
        backoff: values.requestBackoff ?? 'exponential',
        circuitFailureThreshold: values.requestCircuitThreshold ?? 5,
        circuitOpenMs: values.requestCircuitOpenMs ?? 30000,
      };
    case 'python_request':
      return {
        functionName: values.pythonFunctionName ?? 'custom_request',
        authRef: values.pythonAuthRef ?? '',
        code: pythonCode,
        timeoutMs: values.requestTimeoutMs ?? 10000,
        retryAttempts: values.requestRetryAttempts ?? 3,
        backoff: values.requestBackoff ?? 'exponential',
      };
    case 'invoke_workflow':
      return {
        targetWorkflowId: values.invokeTargetWorkflowId ?? '',
        targetWorkflowVersionId: values.invokeTargetWorkflowVersionId ?? '',
        publishedOnly: values.invokePublishedOnly ?? true,
        inputMode: values.invokeInputMode ?? 'inherit',
        inputSource: values.invokeInputSource ?? 'vars.input',
      };
    case 'auth':
      return {
        authType: values.authType ?? 'bearer',
        tokenVar: values.authTokenVar ?? 'vars.token',
        headerName: values.authHeaderName ?? 'Authorization',
      };
    case 'save':
      return {
        key: values.saveKey ?? 'result',
        from: values.saveFrom ?? 'nodes.form_request.output',
      };
    case 'delay':
      return {
        ms: values.delayMs ?? 250,
      };
    case 'raise_error':
      return {
        message: values.raiseErrorMessage ?? 'Failed validation.',
      };
    default:
      return node.data.config;
  }
}

function renderNodeConfigFields(
  node: ApiNode,
  authOptions: Array<{ label: string; value: string }>,
): ReactNode {
  switch (node.data.nodeType) {
    case 'if':
      return (
        <Form.Item label="Expression" name="ifExpression" tooltip="Boolean expression over vars/context.">
          <Input placeholder='vars.status == "ok"' />
        </Form.Item>
      );
    case 'define_variable':
      return (
        <>
          <Form.Item label="Variable Name" name="defineName" rules={[{ required: true }]}>
            <Input placeholder="new_var" />
          </Form.Item>
          <Form.Item label="Source" name="defineSource">
            <Select
              options={[
                { label: 'Last Response', value: 'last_response' },
                { label: 'Node Output', value: 'node_output' },
                { label: 'Context', value: 'context' },
              ]}
            />
          </Form.Item>
          <Form.Item label="Selector" name="defineSelector">
            <Input placeholder="body.data.id" />
          </Form.Item>
          <Form.Item label="Default Value" name="defineDefault">
            <Input placeholder="Optional fallback" />
          </Form.Item>
        </>
      );
    case 'for_each_parallel':
      return (
        <>
          <Form.Item label="List Expression" name="forListExpr" rules={[{ required: true }]}>
            <Input placeholder="vars.items" />
          </Form.Item>
          <Form.Item label="Item Variable" name="forItemName" rules={[{ required: true }]}>
            <Input placeholder="item" />
          </Form.Item>
          <Form.Item label="Max Concurrency" name="forMaxConcurrency">
            <InputNumber min={1} max={100} style={{ width: '100%' }} />
          </Form.Item>
        </>
      );
    case 'join':
      return (
        <Form.Item label="Merge Strategy" name="joinMergeStrategy">
          <Select
            options={[
              { label: 'Collect List', value: 'collect_list' },
              { label: 'Last Write Wins', value: 'last_write_wins' },
              { label: 'Merge Objects', value: 'merge_objects' },
            ]}
          />
        </Form.Item>
      );
    case 'form_request':
      return (
        <>
          <Form.Item label="Method" name="requestMethod">
            <Select
              options={['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((method) => ({
                label: method,
                value: method,
              }))}
            />
          </Form.Item>
          <Form.Item label="URL" name="requestUrl" rules={[{ required: true }]}>
            <Input placeholder="https://api.example.com/resource" />
          </Form.Item>
          <Form.Item label="Auth Reference" name="requestAuthRef">
            <Select allowClear options={authOptions} placeholder="Select auth node" />
          </Form.Item>
          <Form.Item label="Timeout (ms)" name="requestTimeoutMs">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="Retry Attempts" name="requestRetryAttempts">
            <InputNumber min={0} max={10} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="Retry Backoff" name="requestBackoff">
            <Select
              options={[
                { label: 'Exponential', value: 'exponential' },
                { label: 'Fixed', value: 'fixed' },
              ]}
            />
          </Form.Item>
          <Form.Item label="Circuit Failure Threshold" name="requestCircuitThreshold">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="Circuit Open (ms)" name="requestCircuitOpenMs">
            <InputNumber min={100} style={{ width: '100%' }} />
          </Form.Item>
        </>
      );
    case 'python_request':
      return (
        <>
          <Form.Item label="Function Name" name="pythonFunctionName" rules={[{ required: true }]}>
            <Input placeholder="custom_request" />
          </Form.Item>
          <Form.Item label="Auth Reference" name="pythonAuthRef">
            <Select allowClear options={authOptions} placeholder="Select auth node" />
          </Form.Item>
          <Form.Item label="Timeout (ms)" name="requestTimeoutMs">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="Retry Attempts" name="requestRetryAttempts">
            <InputNumber min={0} max={10} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="Retry Backoff" name="requestBackoff">
            <Select
              options={[
                { label: 'Exponential', value: 'exponential' },
                { label: 'Fixed', value: 'fixed' },
              ]}
            />
          </Form.Item>
        </>
      );
    case 'invoke_workflow':
      return (
        <>
          <Form.Item label="Target Workflow ID" name="invokeTargetWorkflowId">
            <Input placeholder="uuid of workflow" />
          </Form.Item>
          <Form.Item label="Target Workflow Version ID" name="invokeTargetWorkflowVersionId">
            <Input placeholder="uuid of specific version" />
          </Form.Item>
          <Form.Item label="Use Latest Published" name="invokePublishedOnly" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item label="Input Mode" name="invokeInputMode">
            <Select
              options={[
                { label: 'Inherit Parent Input', value: 'inherit' },
                { label: 'Use Variable Path', value: 'from_var' },
              ]}
            />
          </Form.Item>
          <Form.Item label="Input Source" name="invokeInputSource" tooltip="Path/expression for child input.">
            <Input placeholder="vars.input" />
          </Form.Item>
        </>
      );
    case 'auth':
      return (
        <>
          <Form.Item label="Auth Type" name="authType">
            <Select
              options={[
                { label: 'Bearer Token', value: 'bearer' },
                { label: 'API Key', value: 'api_key' },
                { label: 'Basic', value: 'basic' },
              ]}
            />
          </Form.Item>
          <Form.Item label="Token Variable" name="authTokenVar">
            <Input placeholder="vars.token" />
          </Form.Item>
          <Form.Item label="Header Name" name="authHeaderName">
            <Input placeholder="Authorization" />
          </Form.Item>
        </>
      );
    case 'save':
      return (
        <>
          <Form.Item label="Save Key" name="saveKey">
            <Input placeholder="result" />
          </Form.Item>
          <Form.Item label="Source Path" name="saveFrom">
            <Input placeholder="nodes.form_request.output" />
          </Form.Item>
        </>
      );
    case 'delay':
      return (
        <Form.Item label="Delay (ms)" name="delayMs">
          <InputNumber min={0} style={{ width: '100%' }} />
        </Form.Item>
      );
    case 'raise_error':
      return (
        <Form.Item label="Message" name="raiseErrorMessage" rules={[{ required: true }]}>
          <Input placeholder="Failed validation." />
        </Form.Item>
      );
    default:
      return <Typography.Text type="secondary">This node has no configurable fields.</Typography.Text>;
  }
}

export default function App() {
  const [nodes, setNodes] = useState<ApiNode[]>(initialNodes);
  const [edges, setEdges] = useState<ApiEdge[]>(initialEdges);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState('');
  const [pythonCode, setPythonCode] = useState('');

  const [form] = Form.useForm<NodeFormValues>();
  const nodeCounterRef = useRef(4);

  const nodeTypes = useMemo(() => ({ apiNode: FlowNode }), []);
  const edgeTypes = useMemo(() => ({ breakpoint: BreakpointEdge }), []);

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  );

  useEffect(() => {
    if (!selectedNode) {
      form.resetFields();
      setPythonCode('');
      return;
    }

    const formValues = configToFormValues(selectedNode);
    form.setFieldsValue(formValues);

    if (selectedNode.data.nodeType === 'python_request') {
      setPythonCode(toStringValue(selectedNode.data.config.code));
    } else {
      setPythonCode('');
    }
  }, [form, selectedNode]);

  const filteredTemplates = useMemo(() => {
    const q = paletteQuery.trim().toLowerCase();
    if (!q) {
      return NODE_TEMPLATES;
    }
    return NODE_TEMPLATES.filter(
      (template) =>
        template.label.toLowerCase().includes(q) || template.type.toLowerCase().includes(q),
    );
  }, [paletteQuery]);

  const authOptions = useMemo(
    () =>
      nodes
        .filter((node) => node.data.nodeType === 'auth')
        .map((node) => ({
          value: node.id,
          label: `${node.data.label} (${node.id})`,
        })),
    [nodes],
  );

  const onNodesChange = useCallback((changes: NodeChange<ApiNode>[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  }, []);

  const onEdgesChange = useCallback((changes: EdgeChange<ApiEdge>[]) => {
    setEdges((current) => applyEdgeChanges(changes, current));
  }, []);

  const onConnect = useCallback((connection: Connection) => {
    const sourceNode = nodes.find((node) => node.id === connection.source);
    const isIfConnection = sourceNode?.data.nodeType === 'if';
    const condition =
      isIfConnection && (connection.sourceHandle === 'true' || connection.sourceHandle === 'false')
        ? connection.sourceHandle
        : undefined;

    const edgeStyle =
      condition === 'true'
        ? { stroke: '#2f9e44', strokeWidth: 2 }
        : condition === 'false'
          ? { stroke: '#c92a2a', strokeWidth: 2 }
          : { stroke: '#44556f', strokeWidth: 1.5 };

    setEdges((current) =>
      addEdge(
        {
          ...connection,
          id: `e-${connection.source}-${connection.target}-${Date.now()}`,
          type: 'breakpoint',
          data: { breakpoint: false, condition },
          label: condition ? condition.toUpperCase() : undefined,
          style: edgeStyle,
        },
        current,
      ) as ApiEdge[],
    );
  }, [nodes]);

  const addNode = useCallback((template: NodeTemplate) => {
    const nextId = `n-${nodeCounterRef.current}`;
    nodeCounterRef.current += 1;

    setNodes((current) => {
      const nextNode = createNodeFromTemplate(template, nextId, current.length);
      return [...current, nextNode];
    });

    setSelectedNodeId(nextId);
    setPaletteOpen(false);
  }, []);

  const onFormValuesChange = useCallback(
    (_: Partial<NodeFormValues>, allValues: NodeFormValues) => {
      if (!selectedNodeId) {
        return;
      }

      setNodes((current) =>
        current.map((node) => {
          if (node.id !== selectedNodeId) {
            return node;
          }

          const nextLabel = allValues.label ?? node.data.label;
          const nextConfig = buildConfigFromValues(node, allValues, pythonCode);

          return {
            ...node,
            data: {
              ...node.data,
              label: nextLabel,
              config: nextConfig,
            },
          };
        }),
      );
    },
    [pythonCode, selectedNodeId],
  );

  const onPythonCodeChange = useCallback(
    (nextCode: string) => {
      setPythonCode(nextCode);
      if (!selectedNodeId) {
        return;
      }

      setNodes((current) =>
        current.map((node) => {
          if (node.id !== selectedNodeId || node.data.nodeType !== 'python_request') {
            return node;
          }

          return {
            ...node,
            data: {
              ...node.data,
              config: {
                ...node.data.config,
                code: nextCode,
              },
            },
          };
        }),
      );
    },
    [selectedNodeId],
  );

  return (
    <Layout className="app-layout">
      <Header className="app-header">
        <div className="brand">API Flow Builder</div>
        <Space>
          <Button type="primary" onClick={() => setPaletteOpen(true)}>
            Open Command Palette
          </Button>
          <Button>Run (POC)</Button>
        </Space>
      </Header>

      <Layout>
        <Sider width={280} theme="light" className="left-sider">
          <Card title="Workflow Tools" size="small">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button type="primary" block onClick={() => setPaletteOpen(true)}>
                Add Node
              </Button>
              <Button block>Validate Graph</Button>
              <Button block>Save Version</Button>
            </Space>
          </Card>
          <Divider />
          <Card title="Node Catalog" size="small">
            <List
              size="small"
              dataSource={NODE_TEMPLATES}
              renderItem={(template) => (
                <List.Item>
                  <Button type="link" onClick={() => addNode(template)}>
                    {template.label}
                  </Button>
                </List.Item>
              )}
            />
          </Card>
        </Sider>

        <Content className="flow-content">
          <ReactFlow<ApiNode, ApiEdge>
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            fitView
            defaultEdgeOptions={{ type: 'breakpoint' }}
          >
            <Background gap={16} size={1} />
            <Controls />
            <MiniMap />
            <Panel position="top-right">
              <Button onClick={() => setPaletteOpen(true)}>+ Node</Button>
            </Panel>
          </ReactFlow>
        </Content>

        <Sider width={360} theme="light" className="right-sider">
          <Card title="Inspector" size="small" className="inspector-card">
            {!selectedNode ? (
              <Typography.Text type="secondary">
                Select a node to edit label and config.
              </Typography.Text>
            ) : (
              <>
                <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }} size="small">
                  <div>
                    <Typography.Text strong>Node</Typography.Text>
                    <div>
                      <Tag>{selectedNode.data.nodeType}</Tag>
                      <Typography.Text type="secondary">{selectedNode.id}</Typography.Text>
                    </div>
                  </div>
                </Space>

                <Form layout="vertical" form={form} onValuesChange={onFormValuesChange}>
                  <Form.Item label="Label" name="label" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>

                  {renderNodeConfigFields(selectedNode, authOptions)}
                </Form>

                {selectedNode.data.nodeType === 'python_request' ? (
                  <div>
                    <Typography.Text strong>Python Code</Typography.Text>
                    <CodeEditor value={pythonCode} onChange={onPythonCodeChange} />
                  </div>
                ) : null}
              </>
            )}
          </Card>
        </Sider>
      </Layout>

      <Drawer
        title="Command Palette"
        width={420}
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
      >
        <Input.Search
          placeholder="Search nodes"
          value={paletteQuery}
          onChange={(event) => setPaletteQuery(event.target.value)}
          allowClear
        />
        <List
          className="palette-list"
          dataSource={filteredTemplates}
          renderItem={(template) => (
            <List.Item
              actions={[
                <Button
                  key={template.type}
                  type="primary"
                  size="small"
                  onClick={() => addNode(template)}
                >
                  Add
                </Button>,
              ]}
            >
              <List.Item.Meta title={template.label} description={template.type} />
            </List.Item>
          )}
        />
      </Drawer>
    </Layout>
  );
}
