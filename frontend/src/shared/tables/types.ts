import type { ReactNode } from 'react';

export type DataTableColumn = {
  id: string;
  label: string;
  align?: 'left' | 'right';
};

export type DataTableRow = {
  id: string;
  href?: string;
  isSelected?: boolean;
  cells: Record<string, ReactNode>;
};
