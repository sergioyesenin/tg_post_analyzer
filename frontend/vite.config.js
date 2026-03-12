import path from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';
var dirname = path.dirname(fileURLToPath(import.meta.url));
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@app': path.resolve(dirname, './src/app'),
            '@shared': path.resolve(dirname, './src/shared'),
            '@modules': path.resolve(dirname, './src/modules'),
            '@test': path.resolve(dirname, './src/test'),
        },
    },
    test: {
        environment: 'jsdom',
        globals: true,
        setupFiles: './src/test/setup.ts',
        css: true,
    },
});
