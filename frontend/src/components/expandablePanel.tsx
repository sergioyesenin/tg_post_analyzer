import type { ReactNode } from "react";

export default function ExpandablePanel({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="mt-3 border rounded-xl bg-gray-50">
      <div className="px-4 py-2 border-b text-sm font-semibold text-gray-700">
        {title}
      </div>

      {/* фиксированная высота + вертикальный скролл */}
      <div className="px-4 py-3 h-72 overflow-y-auto">
        {children}
      </div>
    </div>
  );
}
