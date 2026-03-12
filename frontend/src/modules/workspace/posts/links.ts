export function buildPostDetailHref(postId: number, panel?: 'comments' | 'report') {
  if (!panel) {
    return `/posts/${postId}`;
  }

  return `/posts/${postId}?panel=${panel}`;
}
