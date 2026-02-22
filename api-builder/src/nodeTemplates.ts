import type { NodeTemplate } from './types';

export const NODE_TEMPLATES: NodeTemplate[] = [
  { type: 'start', label: 'Start', defaultConfig: {} },
  { type: 'end', label: 'End', defaultConfig: {} },
  { type: 'if', label: 'If', defaultConfig: { expression: 'vars.status == "ok"' } },
  {
    type: 'define_variable',
    label: 'Define Variable',
    defaultConfig: { name: 'new_var', selector: 'body.data.id', source: 'last_response', defaultValue: '' },
  },
  {
    type: 'for_each_parallel',
    label: 'For Each (Parallel)',
    defaultConfig: { listExpr: 'vars.items', itemName: 'item', maxConcurrency: 5 },
  },
  { type: 'join', label: 'Join', defaultConfig: { mergeStrategy: 'collect_list' } },
  {
    type: 'form_request',
    label: 'Form Request',
    defaultConfig: {
      method: 'GET',
      url: 'https://api.example.com/resource',
      authRef: '',
      timeoutMs: 10000,
      retryAttempts: 3,
      backoff: 'exponential',
      circuitFailureThreshold: 5,
      circuitOpenMs: 30000,
    },
  },
  {
    type: 'python_request',
    label: 'Python Request',
    defaultConfig: {
      functionName: 'custom_request',
      timeoutMs: 10000,
      retryAttempts: 3,
      backoff: 'exponential',
      code: 'def custom_request(context):\n    return {"status_code": 200, "body": {}}\n',
    },
  },
  {
    type: 'invoke_workflow',
    label: 'Invoke Workflow',
    defaultConfig: {
      targetWorkflowId: '',
      targetWorkflowVersionId: '',
      publishedOnly: true,
      inputMode: 'inherit',
      inputSource: 'vars.input',
    },
  },
  {
    type: 'auth',
    label: 'Auth',
    defaultConfig: { authType: 'bearer', tokenVar: 'vars.token', headerName: 'Authorization' },
  },
  { type: 'save', label: 'Save', defaultConfig: { key: 'result', from: 'nodes.form_request.output' } },
  { type: 'delay', label: 'Delay', defaultConfig: { ms: 250 } },
  { type: 'raise_error', label: 'Raise Error', defaultConfig: { message: 'Failed validation.' } },
];
