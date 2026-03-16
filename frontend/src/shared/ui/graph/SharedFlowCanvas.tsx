import type { CSSProperties } from 'react';
import { memo, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from 'reactflow';

export type GraphCanvasTone = 'root' | 'linked' | 'process' | 'event' | 'post' | 'seed' | 'neighbor';

export type GraphCanvasNode = {
  id: string;
  label: string;
  meta?: string;
  tone: GraphCanvasTone;
  href?: string;
  position: { x: number; y: number };
};

export type GraphCanvasEdge = {
  id: string;
  source: string;
  target: string;
  label?: string;
  markerEnd?: boolean;
};

type FlowNodeData = {
  label: string;
  meta?: string;
  tone: GraphCanvasTone;
  href?: string;
  isSelected?: boolean;
  isDimmed?: boolean;
  sourcePosition: Position;
  targetPosition: Position;
};

type SharedFlowCanvasProps = {
  ariaLabel: string;
  nodes: GraphCanvasNode[];
  edges: GraphCanvasEdge[];
  height?: number;
  resetSignal?: number;
  showMiniMap?: boolean;
  showEdgeLabels?: boolean;
  sourcePosition?: Position;
  targetPosition?: Position;
};

const toneStyles: Record<GraphCanvasTone, CSSProperties> = {
  root: { borderColor: '#b64926', background: 'rgba(182, 73, 38, 0.14)' },
  linked: { borderColor: '#0f4c75', background: 'rgba(15, 76, 117, 0.1)' },
  process: { borderColor: '#7c4d1f', background: 'rgba(124, 77, 31, 0.12)' },
  event: { borderColor: '#2d6a4f', background: 'rgba(45, 106, 79, 0.12)' },
  post: { borderColor: '#0f4c75', background: 'rgba(15, 76, 117, 0.08)' },
  seed: { borderColor: '#b64926', background: 'rgba(182, 73, 38, 0.14)' },
  neighbor: { borderColor: '#576579', background: 'rgba(87, 101, 121, 0.12)' },
};

const nodeColorByTone: Record<GraphCanvasTone, string> = {
  root: '#b64926',
  linked: '#0f4c75',
  process: '#7c4d1f',
  event: '#2d6a4f',
  post: '#0f4c75',
  seed: '#b64926',
  neighbor: '#576579',
};

const GraphCardNode = memo(function GraphCardNode({ data }: NodeProps<FlowNodeData>) {
  return (
    <>
      <Handle type="target" position={data.targetPosition} className="graph-flow-canvas__handle" />
      <div
        className={`graph-flow-canvas__node ${data.isSelected ? 'graph-flow-canvas__node--selected' : ''} ${data.isDimmed ? 'graph-flow-canvas__node--dimmed' : ''}`.trim()}
        style={toneStyles[data.tone]}
      >
        <strong>{data.label}</strong>
        {data.meta ? <span>{data.meta}</span> : null}
        {data.href ? <Link className="table-link" to={data.href}>Open</Link> : null}
      </div>
      <Handle type="source" position={data.sourcePosition} className="graph-flow-canvas__handle" />
    </>
  );
});

const nodeTypes = {
  graphCard: GraphCardNode,
};

function FlowViewportReset({ resetSignal }: { resetSignal: number }) {
  const reactFlow = useReactFlow();

  useEffect(() => {
    reactFlow.fitView({ padding: 0.24, duration: 250 });
  }, [reactFlow, resetSignal]);

  return null;
}

function SharedFlowCanvasInner({
  ariaLabel,
  nodes,
  edges,
  height = 320,
  resetSignal = 0,
  showMiniMap = true,
  showEdgeLabels = true,
  sourcePosition = Position.Right,
  targetPosition = Position.Left,
}: SharedFlowCanvasProps) {
  const isTestMode = import.meta.env.MODE === 'test';
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const shouldShowMiniMap = showMiniMap && nodes.length > 4;

  useEffect(() => {
    setSelectedNodeId(null);
  }, [ariaLabel, resetSignal]);

  const connectedNodeIds = useMemo(() => {
    if (!selectedNodeId) {
      return new Set<string>();
    }

    const ids = new Set<string>([selectedNodeId]);
    edges.forEach((edge) => {
      if (edge.source === selectedNodeId) {
        ids.add(edge.target);
      }
      if (edge.target === selectedNodeId) {
        ids.add(edge.source);
      }
    });
    return ids;
  }, [edges, selectedNodeId]);

  const flowNodes = useMemo<Node<FlowNodeData>[]>(
    () =>
      nodes.map((node) => {
        const isSelected = node.id === selectedNodeId;
        const isDimmed = selectedNodeId !== null && !connectedNodeIds.has(node.id);

        return {
          id: node.id,
          type: 'graphCard',
          position: node.position,
          sourcePosition,
          targetPosition,
          data: {
            label: node.label,
            meta: node.meta,
            tone: node.tone,
            href: node.href,
            isSelected,
            isDimmed,
            sourcePosition,
            targetPosition,
          },
        };
      }),
    [connectedNodeIds, nodes, selectedNodeId, sourcePosition, targetPosition],
  );

  const flowEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge) => {
        const isConnected =
          selectedNodeId !== null && (edge.source === selectedNodeId || edge.target === selectedNodeId);
        const isDimmed = selectedNodeId !== null && !isConnected;
        const stroke = isConnected ? '#b64926' : '#8a5a34';
        const edgeHasMarker = edge.markerEnd !== false;

        return {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          label: showEdgeLabels ? edge.label : undefined,
          type: 'smoothstep',
          animated: isConnected,
          zIndex: isConnected ? 2 : 1,
          markerEnd: edgeHasMarker
            ? {
                type: MarkerType.ArrowClosed,
                color: stroke,
                width: 20,
                height: 20,
              }
            : undefined,
          style: {
            stroke,
            strokeWidth: isConnected ? 3 : 2,
            opacity: isDimmed ? 0.22 : 0.88,
          },
          labelStyle: { fill: stroke, fontSize: 11, fontWeight: 600 },
          labelBgStyle: { fill: '#fffaf2', fillOpacity: 0.92 },
          labelBgPadding: [6, 3],
          interactionWidth: 24,
        };
      }),
    [edges, selectedNodeId, showEdgeLabels],
  );

  if (isTestMode) {
    return (
      <div className="graph-flow-canvas graph-flow-canvas--test" aria-label={ariaLabel}>
        <span>{nodes.length} nodes</span>
        <span>{edges.length} edges</span>
        <span>{selectedNodeId ? `selected ${selectedNodeId}` : 'no selection'}</span>
      </div>
    );
  }

  return (
    <div className="graph-flow-canvas" style={{ height }} aria-label={ariaLabel}>
      <ReactFlow
        fitView
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={{ type: 'smoothstep' }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        panOnScroll
        zoomOnScroll
        minZoom={0.45}
        onNodeClick={(_, node) => setSelectedNodeId(node.id)}
        onPaneClick={() => setSelectedNodeId(null)}
        proOptions={{ hideAttribution: true }}
      >
        <FlowViewportReset resetSignal={resetSignal} />
        {shouldShowMiniMap ? (
          <MiniMap
            pannable
            zoomable
            nodeColor={(node) => nodeColorByTone[(node.data as FlowNodeData).tone]}
            maskColor="rgba(255, 250, 242, 0.65)"
          />
        ) : null}
        <Controls showInteractive={false} />
        <Background color="rgba(87, 101, 121, 0.2)" gap={20} />
      </ReactFlow>
    </div>
  );
}

export function SharedFlowCanvas(props: SharedFlowCanvasProps) {
  return (
    <ReactFlowProvider>
      <SharedFlowCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
