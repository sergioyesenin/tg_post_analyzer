import { RoutePlaceholder } from '@shared/ui/placeholders/RoutePlaceholder';

export function PostDetailsPlaceholderPage() {
  return (
    <RoutePlaceholder
      eyebrow="posts/:postId"
      title="Post details placeholder"
      description="Detail composition stays out of scope for stage 0. The route exists so navigation, guards and module boundaries can stabilize early."
    />
  );
}
