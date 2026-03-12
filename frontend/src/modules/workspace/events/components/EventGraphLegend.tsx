export function EventGraphLegend() {
  return (
    <div className="event-graph-legend" aria-label="Event graph legend">
      <span className="event-graph-legend__item">
        <span className="event-graph-legend__swatch event-graph-legend__swatch--root" />
        Root post
      </span>
      <span className="event-graph-legend__item">
        <span className="event-graph-legend__swatch event-graph-legend__swatch--node" />
        Related post
      </span>
      <span className="event-graph-legend__item">
        <span className="event-graph-legend__swatch event-graph-legend__swatch--edge" />
        Link edge
      </span>
    </div>
  );
}
