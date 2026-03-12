export type QueryValue = string | number | boolean | Array<string | number | boolean> | undefined | null;

export function parseQueryParams(search: string) {
  const params = new URLSearchParams(search);
  const result: Record<string, string | string[]> = {};

  for (const key of new Set(params.keys())) {
    const values = params.getAll(key);
    result[key] = values.length > 1 ? values : values[0] ?? '';
  }

  return result;
}

export function serializeQueryParams(query: Record<string, QueryValue>) {
  const params = new URLSearchParams();

  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }

    if (Array.isArray(value)) {
      value.forEach((item) => params.append(key, String(item)));
      return;
    }

    params.set(key, String(value));
  });

  return params.toString();
}
