import type { PropsWithChildren } from 'react';
import { createContext, useContext } from 'react';

import { themeTokens } from '@shared/theme/tokens';

type ThemeContextValue = {
  themeName: string;
};

const ThemeContext = createContext<ThemeContextValue>({ themeName: 'analytics' });

export function ThemeProvider({ children }: PropsWithChildren) {
  return (
    <ThemeContext.Provider value={{ themeName: themeTokens.name }}>
      <div data-theme={themeTokens.name}>{children}</div>
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
