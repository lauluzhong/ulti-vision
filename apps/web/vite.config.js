import { defineConfig } from 'vite';
import { sveltekit } from '@sveltejs/kit/vite';

const proxyTarget = process.env.SVA_API_PROXY_TARGET || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
});
