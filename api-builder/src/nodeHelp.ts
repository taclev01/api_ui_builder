import type { ApiNodeType } from './types';

export type NodeHelp = {
  title: string;
  description: string;
  references: string[];
};

export const NODE_HELP: Record<ApiNodeType, NodeHelp> = {
  start_python: {
    title: 'Start (Python)',
    description: 'Runs first and can prepare initial context values before the flow continues.',
    references: ['Return values under context vars, then consume as vars.<name> in later nodes.'],
  },
  start_request: {
    title: 'Start (Request)',
    description: 'Runs an initial request to bootstrap the workflow context.',
    references: ['Extract response values using Define Variable and reference as vars.<name>.'],
  },
  end: {
    title: 'End',
    description: 'Terminal success node. No outgoing flow edges.',
    references: ['Use Save nodes before End if output materialization is needed.'],
  },
  if: {
    title: 'If',
    description: 'Branches flow using TRUE/FALSE outputs based on an expression over context.',
    references: [
      'Expression examples: vars.status == "ok"',
      'Must connect exactly one TRUE edge and one FALSE edge.',
    ],
  },
  define_variable: {
    title: 'Define Variable',
    description: 'Extracts or computes named values for reuse by later nodes.',
    references: ['Defined values are read as vars.<name>.'],
  },
  for_each_parallel: {
    title: 'For Each (Parallel)',
    description: 'Iterates list-like input values with parallel-style semantics (POC behavior).',
    references: ['Point list expression at a value like vars.items.'],
  },
  join: {
    title: 'Join',
    description: 'Combines branch outputs back into a single path.',
    references: ['Set merge strategy to control conflict behavior.'],
  },
  form_request: {
    title: 'Form Request',
    description: 'Declarative HTTP request node with retry/timeout/circuit settings.',
    references: ['Choose an Auth node by ID via Auth Reference.'],
  },
  paginate_request: {
    title: 'Paginate Request',
    description: 'Fetches multiple pages using pagination strategy and aggregates results.',
    references: [
      'Set items path, cursor paths, and max pages.',
      'Use strategy fields to match API style (next URL, cursor, page number, offset/limit).',
    ],
  },
  python_request: {
    title: 'Python Request',
    description: 'Executes custom Python logic for complex request behavior.',
    references: ['Select auth via Auth Reference and read values from vars.<name>.'],
  },
  invoke_workflow: {
    title: 'Invoke Workflow',
    description: 'Calls another workflow version as a child execution.',
    references: ['Pass input context values and track lineage with parent/child execution IDs.'],
  },
  auth: {
    title: 'Auth',
    description: 'Data-only auth definition node. Not connected by edges.',
    references: [
      'Reference this node from request nodes using Auth Reference selector.',
      'Common variable path: vars.token.',
    ],
  },
  parameters: {
    title: 'Parameters',
    description: 'Data-only parameter definitions for reusable runtime inputs.',
    references: [
      'Parameters should be mirrored to context vars and accessed as vars.<parameter_name>.',
      'Use Define Variable to normalize parameter values for downstream nodes.',
    ],
  },
  save: {
    title: 'Save',
    description: 'Persists selected values from context/node outputs.',
    references: ['Source paths typically use vars.<name> or nodes.<node_id>.output.'],
  },
  delay: {
    title: 'Delay',
    description: 'Adds a pause in workflow execution.',
    references: ['Useful for rate-limits and pacing between requests.'],
  },
  raise_error: {
    title: 'Raise Error',
    description: 'Terminal failure node that stops execution with a configured message.',
    references: ['Use for explicit guardrail failures and validation aborts.'],
  },
};

export const QUICK_REFERENCE = [
  'Context variables: vars.<name>',
  'Node outputs: nodes.<node_id>.output (example: nodes.n-2.output)',
  'Find node IDs by selecting a node in Inspector and using Copy ID',
  'Auth references: choose an Auth node in request forms',
  'Parameter flow: define in Parameters node, map to vars for usage',
  'If node outputs: source handles true and false',
  'Breakpoints: click red edge dot to toggle debug pause',
];
