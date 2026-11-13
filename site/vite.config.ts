import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  server: {
    // Bind strictly to loopback per mandatory secure coding rules (never 0.0.0.0)
    host: '127.0.0.1',
    port: 4173,
    strictPort: false,
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: false,
  },
  build: {
    outDir: 'dist',
    assetsDir: 'chunks',
    sourcemap: false,
    target: 'es2022',
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ['three'],
        },
      },
    },
  },
});
