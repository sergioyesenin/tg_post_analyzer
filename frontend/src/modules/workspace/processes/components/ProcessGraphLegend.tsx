export function ProcessGraphLegend() {
  return (
    <div className="process-graph-legend" aria-label="Process graph legend">
      <span className="process-graph-legend__item">
        <span className="process-graph-legend__swatch process-graph-legend__swatch--process" />
        Process layer
      </span>
      <span className="process-graph-legend__item">
        <span className="process-graph-legend__swatch process-graph-legend__swatch--event" />
        Nested event
      </span>
      <span className="process-graph-legend__item">
        <span className="process-graph-legend__swatch process-graph-legend__swatch--post" />
        Context post
      </span>
      <span className="process-graph-legend__item">
        <span className="process-graph-legend__swatch process-graph-legend__swatch--edge" />
        Post link
      </span>
    </div>
  );
}
