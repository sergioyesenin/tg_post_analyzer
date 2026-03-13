type ProcessGraphToolbarProps = {
  title: string;
  eventCount: number;
  postCount: number;
  isLoading: boolean;
  onRefresh: () => void;
};

export function ProcessGraphToolbar({
  title,
  eventCount,
  postCount,
  isLoading,
  onRefresh,
}: ProcessGraphToolbarProps) {
  return (
    <div className="process-graph-toolbar">
      <div>
        <span className="state-card__eyebrow">hierarchy toolbar</span>
        <strong>{title}</strong>
      </div>
      <div className="process-graph-toolbar__meta">
        <span>{eventCount} events</span>
        <span>{postCount} posts</span>
        <button type="button" className="dashboard-button dashboard-button--ghost" onClick={onRefresh} disabled={isLoading}>
          Reload graph
        </button>
      </div>
    </div>
  );
}
