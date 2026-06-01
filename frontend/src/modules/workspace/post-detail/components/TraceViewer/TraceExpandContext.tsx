import { createContext, useContext, useState, ReactNode } from 'react';

type TraceExpandContextValue = {
  expandedSteps: Record<string, boolean>;
  toggleStep: (stepId: string) => void;
  expandAll: () => void;
  collapseAll: () => void;
};

const TraceExpandContext = createContext<TraceExpandContextValue | null>(null);

export function TraceExpandProvider({ children }: { children: ReactNode }) {
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({});

  const toggleStep = (stepId: string) => {
    setExpandedSteps(prev => ({ ...prev, [stepId]: !prev[stepId] }));
  };

  const expandAll = () => {
    const allIds = ['context', 'routing', 'expert', 'public_opinion', 'synthesis', 'reviewer'];
    const newState: Record<string, boolean> = {};
    allIds.forEach(id => { newState[id] = true; });
    setExpandedSteps(newState);
  };

  const collapseAll = () => {
    setExpandedSteps({});
  };

  return (
    <TraceExpandContext.Provider value={{ expandedSteps, toggleStep, expandAll, collapseAll }}>
      {children}
    </TraceExpandContext.Provider>
  );
}

export function useTraceExpand() {
  const ctx = useContext(TraceExpandContext);
  if (!ctx) throw new Error('useTraceExpand must be used within TraceExpandProvider');
  return ctx;
}