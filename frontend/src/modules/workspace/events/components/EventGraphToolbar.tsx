type EventGraphToolbarProps = {
  title: string;
  nodeCount: number;
  edgeCount: number;
  isLoading: boolean;
  onRefresh: () => void;
};

export function EventGraphToolbar({ title, nodeCount, edgeCount, isLoading, onRefresh }: EventGraphToolbarProps) {
  return (
    <div className="event-graph-toolbar">
      <div>
        <span className="state-card__eyebrow">graph toolbar</span>
        <strong>{title}</strong>
      </div>
      <div className="event-graph-toolbar__meta">
        <span>{nodeCount} nodes</span>
        <span>{edgeCount} edges</span>
        <button type="button" className="dashboard-button dashboard-button--ghost" onClick={onRefresh} disabled={isLoading}>
          Reload graph
        </button>
      </div>
    </div>
  );
}
