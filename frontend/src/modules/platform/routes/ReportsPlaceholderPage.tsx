import { useParams } from 'react-router-dom';

import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function ReportsPlaceholderPage() {
  const { reportType = 'unknown' } = useParams();

  return (
    <RoutePlaceholder
      eyebrow={`reports/${reportType}`}
      title="Reports catalog placeholder"
      description="Route-level ownership for report catalog pages is ready. Table contracts and export flows stay for later stages."
    />
  );
}
