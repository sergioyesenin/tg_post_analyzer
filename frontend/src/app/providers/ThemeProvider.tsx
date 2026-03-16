import type { PropsWithChildren } from 'react';
import { createContext, useContext } from 'react';
import { CssBaseline } from '@mui/material';
import { ThemeProvider as MuiThemeProvider, createTheme } from '@mui/material/styles';

import { themeTokens } from '@shared/theme/tokens';

type ThemeContextValue = {
  themeName: string;
};

const ThemeContext = createContext<ThemeContextValue>({ themeName: 'analytics' });

const muiTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: themeTokens.color.accent,
    },
    success: {
      main: themeTokens.color.success,
    },
    warning: {
      main: themeTokens.color.warning,
    },
    error: {
      main: themeTokens.color.danger,
    },
    background: {
      default: themeTokens.color.background,
      paper: themeTokens.color.surface,
    },
    text: {
      primary: themeTokens.color.text,
      secondary: themeTokens.color.muted,
    },
  },
  shape: {
    borderRadius: themeTokens.radius.sm,
  },
  typography: {
    fontFamily: 'IBM Plex Sans, Segoe UI, sans-serif',
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
      },
    },
  },
});

export function ThemeProvider({ children }: PropsWithChildren) {
  return (
    <ThemeContext.Provider value={{ themeName: themeTokens.name }}>
      <MuiThemeProvider theme={muiTheme}>
        <CssBaseline />
        <div data-theme={themeTokens.name}>{children}</div>
      </MuiThemeProvider>
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
