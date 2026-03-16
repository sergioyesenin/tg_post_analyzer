import path from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

const dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, dirname, '');
  const apiTarget = env.VITE_API_PROXY_TARGET || env.VITE_API_BASE_URL || 'http://localhost:8000';

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@app': path.resolve(dirname, './src/app'),
        '@shared': path.resolve(dirname, './src/shared'),
        '@modules': path.resolve(dirname, './src/modules'),
        '@test': path.resolve(dirname, './src/test'),
      },
    },
    server: {
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) {
              return undefined;
            }

            if (id.includes('reactflow')) {
              return 'graph-vendor';
            }

            if (id.includes('@mui') || id.includes('@emotion')) {
              return 'mui-vendor';
            }

            if (id.includes('i18next')) {
              return 'i18n-vendor';
            }

            return 'vendor';
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/test/setup.ts',
      css: true,
    },
  };
});
