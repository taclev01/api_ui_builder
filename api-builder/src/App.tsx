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
  Collapse,
  Divider,
  Drawer,
  Form,
  Input,
  InputNumber,
  Layout,
  Modal,
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
import type { ApiEdge, ApiNode, NodeCategory, NodeTemplate } from './types';

import '@xyflow/react/dist/style.css';
import './App.css';

const { Header, Content, Sider } = Layout;

type NodeFormValues = {
  label?: string;
  startPythonFunctionName?: string;
  startRequestMethod?: string;
  startRequestUrl?: string;
  startRequestAuthRef?: string;
  startRequestTimeoutMs?: number;
  startRequestRetryAttempts?: number;
  startRequestBackoff?: string;
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
  paginateStrategy?: string;
  paginateItemsPath?: string;
  paginateNextCursorPath?: string;
  paginateHasMorePath?: string;
  paginateMaxPages?: number;
  paginatePageSize?: number;
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
  parametersList?: ParameterItem[];
};

type ParameterItem = {
  name?: string;
  type?: string;
  defaultValue?: string;
  description?: string;
};

const initialNodes: ApiNode[] = [
  {
    id: 'n-1',
    type: 'apiNode',
    position: { x: 140, y: 120 },
    data: {
      label: 'Start (Request)',
      nodeType: 'start_request',
      config: {
        method: 'GET',
        url: 'https://api.example.com/bootstrap',
        authRef: '',
        timeoutMs: 10000,
        retryAttempts: 3,
        backoff: 'exponential',
      },
    },
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
    case 'start_python':
      return {
        ...baseValues,
        startPythonFunctionName: toStringValue(config.functionName, 'setup_context'),
      };
    case 'start_request':
      return {
        ...baseValues,
        startRequestMethod: toStringValue(config.method, 'GET'),
        startRequestUrl: toStringValue(config.url, 'https://api.example.com/bootstrap'),
        startRequestAuthRef: toStringValue(config.authRef),
        startRequestTimeoutMs: toNumberValue(config.timeoutMs, 10000),
        startRequestRetryAttempts: toNumberValue(config.retryAttempts, 3),
        startRequestBackoff: toStringValue(config.backoff, 'exponential'),
      };
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
    case 'paginate_request':
      return {
        ...baseValues,
        requestMethod: toStringValue(config.method, 'GET'),
        requestUrl: toStringValue(config.url, 'https://api.example.com/resources'),
        requestAuthRef: toStringValue(config.authRef),
        paginateStrategy: toStringValue(config.strategy, 'next_url'),
        paginateItemsPath: toStringValue(config.itemsPath, 'body.items'),
        paginateNextCursorPath: toStringValue(config.nextCursorPath, 'body.next'),
        paginateHasMorePath: toStringValue(config.hasMorePath, 'body.has_more'),
        paginateMaxPages: toNumberValue(config.maxPages, 25),
        paginatePageSize: toNumberValue(config.pageSize, 100),
        requestTimeoutMs: toNumberValue(config.timeoutMs, 10000),
        requestRetryAttempts: toNumberValue(config.retryAttempts, 3),
        requestBackoff: toStringValue(config.backoff, 'exponential'),
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
    case 'parameters':
      return {
        ...baseValues,
        parametersList: Array.isArray(config.parameters)
          ? (config.parameters as ParameterItem[])
          : [{ name: 'date', type: 'string', defaultValue: '', description: 'Date parameter' }],
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
    case 'start_python':
      return {
        functionName: values.startPythonFunctionName ?? 'setup_context',
        code: pythonCode,
      };
    case 'start_request':
      return {
        method: values.startRequestMethod ?? 'GET',
        url: values.startRequestUrl ?? '',
        authRef: values.startRequestAuthRef ?? '',
        timeoutMs: values.startRequestTimeoutMs ?? 10000,
        retryAttempts: values.startRequestRetryAttempts ?? 3,
        backoff: values.startRequestBackoff ?? 'exponential',
      };
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
    case 'paginate_request':
      return {
        method: values.requestMethod ?? 'GET',
        url: values.requestUrl ?? '',
        authRef: values.requestAuthRef ?? '',
        strategy: values.paginateStrategy ?? 'next_url',
        itemsPath: values.paginateItemsPath ?? 'body.items',
        nextCursorPath: values.paginateNextCursorPath ?? 'body.next',
        hasMorePath: values.paginateHasMorePath ?? 'body.has_more',
        maxPages: values.paginateMaxPages ?? 25,
        pageSize: values.paginatePageSize ?? 100,
        timeoutMs: values.requestTimeoutMs ?? 10000,
        retryAttempts: values.requestRetryAttempts ?? 3,
        backoff: values.requestBackoff ?? 'exponential',
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
    case 'parameters':
      return {
        parameters: (values.parametersList ?? []).map((item) => ({
          name: item.name ?? '',
          type: item.type ?? 'string',
          defaultValue: item.defaultValue ?? '',
          description: item.description ?? '',
        })),
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
    case 'start_python':
      return (
        <Form.Item
          label="Setup Function Name"
          name="startPythonFunctionName"
          tooltip="Runs first and can prepare context/loop values."
          rules={[{ required: true }]}
        >
          <Input placeholder="setup_context" />
        </Form.Item>
      );
    case 'start_request':
      return (
        <>
          <Form.Item label="Method" name="startRequestMethod">
            <Select
              options={['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((method) => ({
                label: method,
                value: method,
              }))}
            />
          </Form.Item>
          <Form.Item label="URL" name="startRequestUrl" rules={[{ required: true }]}>
            <Input placeholder="https://api.example.com/bootstrap" />
          </Form.Item>
          <Form.Item label="Auth Reference" name="startRequestAuthRef">
            <Select allowClear options={authOptions} placeholder="Select auth node" />
          </Form.Item>
          <Form.Item label="Timeout (ms)" name="startRequestTimeoutMs">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="Retry Attempts" name="startRequestRetryAttempts">
            <InputNumber min={0} max={10} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="Retry Backoff" name="startRequestBackoff">
            <Select
              options={[
                { label: 'Exponential', value: 'exponential' },
                { label: 'Fixed', value: 'fixed' },
              ]}
            />
          </Form.Item>
        </>
      );
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
    case 'paginate_request':
      return (
        <>
          <Form.Item label="Method" name="requestMethod">
            <Select
              options={['GET', 'POST'].map((method) => ({
                label: method,
                value: method,
              }))}
            />
          </Form.Item>
          <Form.Item label="URL" name="requestUrl" rules={[{ required: true }]}>
            <Input placeholder="https://api.example.com/resources" />
          </Form.Item>
          <Form.Item label="Auth Reference" name="requestAuthRef">
            <Select allowClear options={authOptions} placeholder="Select auth node" />
          </Form.Item>
          <Form.Item label="Pagination Strategy" name="paginateStrategy">
            <Select
              options={[
                { label: 'Next URL', value: 'next_url' },
                { label: 'Cursor Param', value: 'cursor_param' },
                { label: 'Page Number', value: 'page_number' },
                { label: 'Offset/Limit', value: 'offset_limit' },
              ]}
            />
          </Form.Item>
          <Form.Item label="Items Path" name="paginateItemsPath">
            <Input placeholder="body.items" />
          </Form.Item>
          <Form.Item label="Next Cursor Path" name="paginateNextCursorPath">
            <Input placeholder="body.next" />
          </Form.Item>
          <Form.Item label="Has More Path" name="paginateHasMorePath">
            <Input placeholder="body.has_more" />
          </Form.Item>
          <Form.Item label="Max Pages" name="paginateMaxPages">
            <InputNumber min={1} max={10000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="Page Size" name="paginatePageSize">
            <InputNumber min={1} max={10000} style={{ width: '100%' }} />
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
    case 'parameters':
      return (
        <Form.List name="parametersList">
          {(fields, { add, remove }) => (
            <Space direction="vertical" style={{ width: '100%' }} size={8}>
              <Collapse
                className="parameter-collapse"
                size="small"
                items={fields.map((field, index) => ({
                  key: String(field.key),
                  label: `Parameter ${index + 1}`,
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }} size={8}>
                      <Form.Item label="Name" name={[field.name, 'name']} rules={[{ required: true }]}>
                        <Input placeholder="date" />
                      </Form.Item>
                      <Form.Item label="Type" name={[field.name, 'type']}>
                        <Select
                          options={[
                            { label: 'String', value: 'string' },
                            { label: 'Number', value: 'number' },
                            { label: 'Boolean', value: 'boolean' },
                            { label: 'List', value: 'list' },
                            { label: 'Object', value: 'object' },
                          ]}
                        />
                      </Form.Item>
                      <Form.Item label="Default Value" name={[field.name, 'defaultValue']}>
                        <Input />
                      </Form.Item>
                      <Form.Item label="Description" name={[field.name, 'description']}>
                        <Input />
                      </Form.Item>
                      <Button danger block onClick={() => remove(field.name)}>
                        Remove Parameter
                      </Button>
                    </Space>
                  ),
                }))}
              />
              <Button block onClick={() => add({ name: '', type: 'string', defaultValue: '', description: '' })}>
                Add Parameter
              </Button>
            </Space>
          )}
        </Form.List>
      );
    default:
      return <Typography.Text type="secondary">This node has no configurable fields.</Typography.Text>;
  }
}

function validateGraph(nodes: ApiNode[], edges: ApiEdge[]): string[] {
  const errors: string[] = [];
  const startTypes = new Set(['start_python', 'start_request']);
  const terminalTypes = new Set(['end', 'raise_error']);
  const dataOnlyTypes = new Set(['auth', 'parameters']);

  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const outgoing = new Map<string, ApiEdge[]>();
  const incoming = new Map<string, ApiEdge[]>();

  for (const edge of edges) {
    outgoing.set(edge.source, [...(outgoing.get(edge.source) ?? []), edge]);
    incoming.set(edge.target, [...(incoming.get(edge.target) ?? []), edge]);
  }

  const startNodes = nodes.filter((node) => startTypes.has(node.data.nodeType));
  if (startNodes.length !== 1) {
    errors.push(`Graph must contain exactly 1 start node. Found ${startNodes.length}.`);
  }

  for (const node of nodes) {
    const nodeType = node.data.nodeType;
    const out = outgoing.get(node.id) ?? [];
    const inc = incoming.get(node.id) ?? [];

    if (startTypes.has(nodeType) && inc.length > 0) {
      errors.push(`Start node "${node.data.label}" cannot have incoming edges.`);
    }

    if (terminalTypes.has(nodeType) && out.length > 0) {
      errors.push(`Terminal node "${node.data.label}" cannot have outgoing edges.`);
    }

    if (dataOnlyTypes.has(nodeType) && (inc.length > 0 || out.length > 0)) {
      errors.push(`Data-only node "${node.data.label}" must not have graph edges.`);
    }

    if (nodeType === 'if') {
      const trueEdges = out.filter((edge) => edge.data?.condition === 'true').length;
      const falseEdges = out.filter((edge) => edge.data?.condition === 'false').length;
      if (trueEdges !== 1 || falseEdges !== 1) {
        errors.push(`If node "${node.data.label}" must have exactly one TRUE edge and one FALSE edge.`);
      }
    }
  }

  const startNode = startNodes[0];
  if (!startNode) {
    return errors;
  }

  const visiting = new Set<string>();
  const visited = new Set<string>();
  const reachable = new Set<string>();

  const dfs = (nodeId: string): void => {
    if (visiting.has(nodeId)) {
      errors.push(`Cycle detected at node "${nodesById.get(nodeId)?.data.label ?? nodeId}".`);
      return;
    }
    if (visited.has(nodeId)) {
      return;
    }

    visiting.add(nodeId);
    reachable.add(nodeId);

    const node = nodesById.get(nodeId);
    const nodeType = node?.data.nodeType;
    const nextEdges = outgoing.get(nodeId) ?? [];

    if (node && !terminalTypes.has(nodeType ?? '') && !dataOnlyTypes.has(nodeType ?? '') && nextEdges.length === 0) {
      errors.push(`Node "${node.data.label}" is a dead-end and never reaches a terminal node.`);
    }

    for (const edge of nextEdges) {
      dfs(edge.target);
    }

    visiting.delete(nodeId);
    visited.add(nodeId);
  };

  dfs(startNode.id);

  const reachableTerminals = [...reachable].filter((nodeId) =>
    terminalTypes.has(nodesById.get(nodeId)?.data.nodeType ?? ''),
  );
  if (reachableTerminals.length === 0) {
    errors.push('No reachable terminal node found (End or Raise Error).');
  }

  return Array.from(new Set(errors));
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

    if (selectedNode.data.nodeType === 'python_request' || selectedNode.data.nodeType === 'start_python') {
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

  const groupedTemplates = useMemo(() => {
    return filteredTemplates.reduce<Record<NodeCategory, NodeTemplate[]>>(
      (acc, template) => {
        acc[template.category].push(template);
        return acc;
      },
      {
        Lifecycle: [],
        Auth: [],
        Control: [],
        Requests: [],
        Save: [],
        Utility: [],
      },
    );
  }, [filteredTemplates]);

  const allGroupedTemplates = useMemo(() => {
    return NODE_TEMPLATES.reduce<Record<NodeCategory, NodeTemplate[]>>(
      (acc, template) => {
        acc[template.category].push(template);
        return acc;
      },
      {
        Lifecycle: [],
        Auth: [],
        Control: [],
        Requests: [],
        Save: [],
        Utility: [],
      },
    );
  }, []);

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
          if (
            node.id !== selectedNodeId ||
            (node.data.nodeType !== 'python_request' && node.data.nodeType !== 'start_python')
          ) {
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

  const onValidateGraph = useCallback(() => {
    const errors = validateGraph(nodes, edges);
    if (errors.length === 0) {
      Modal.success({
        title: 'Graph Validation Passed',
        content: 'No blocking issues were found.',
      });
      return;
    }

    Modal.error({
      title: `Graph Validation Failed (${errors.length})`,
      width: 680,
      content: (
        <ul>
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      ),
    });
  }, [edges, nodes]);

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
              <Button block onClick={onValidateGraph}>
                Validate Graph
              </Button>
              <Button block>Save Version</Button>
            </Space>
          </Card>
          <Divider />
          <Card title="Node Catalog" size="small">
            <Collapse
              size="small"
              ghost
              items={(Object.keys(allGroupedTemplates) as NodeCategory[]).map((category) => ({
                key: category,
                label: category,
                children: (
                  <Space direction="vertical" style={{ width: '100%' }} size={4}>
                    {allGroupedTemplates[category].map((template) => (
                      <Button
                        key={template.type}
                        type="text"
                        className="catalog-item-btn"
                        onClick={() => addNode(template)}
                      >
                        {template.label}
                      </Button>
                    ))}
                  </Space>
                ),
              }))}
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

                {selectedNode.data.nodeType === 'python_request' || selectedNode.data.nodeType === 'start_python' ? (
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
        onClose={() => {
          setPaletteOpen(false);
        }}
      >
        <Input.Search
          placeholder="Search nodes"
          value={paletteQuery}
          onChange={(event) => setPaletteQuery(event.target.value)}
          allowClear
        />
        <Collapse
          className="palette-collapse"
          items={(Object.keys(groupedTemplates) as NodeCategory[])
            .filter((category) => groupedTemplates[category].length > 0)
            .map((category) => ({
              key: category,
              label: category,
              children: (
                <Space direction="vertical" style={{ width: '100%' }} size={6}>
                  {groupedTemplates[category].map((template) => (
                    <Button
                      key={template.type}
                      className="palette-item-btn"
                      onClick={() => addNode(template)}
                    >
                      {template.label}
                    </Button>
                  ))}
                </Space>
              ),
            }))}
        />
      </Drawer>
    </Layout>
  );
}
