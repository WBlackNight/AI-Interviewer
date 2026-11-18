import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, process.cwd(), 'QINGZHAN_');
  const backendPort = Number(
    process.env.QINGZHAN_DEV_PORT || environment.QINGZHAN_DEV_PORT || 8000
  );
  if (!Number.isInteger(backendPort) || backendPort < 1 || backendPort > 65535)
    throw new Error('Invalid QINGZHAN_DEV_PORT');
  const backend = 'http://127.0.0.1:' + backendPort;

  return {
    plugins: [
      react(),
      {
        name: 'qingzhan-page-routes',
        configureServer(server) {
          server.middlewares.use((req, _res, next) => {
            const path = (req.url || '').split('?')[0];
            if (path === '/assistant') req.url = '/assistant.html';
            if (path === '/admin') req.url = '/admin.html';
            const mode = new URL(req.url || '/', 'http://127.0.0.1').searchParams.get('mode');
            if (/^\/interview\/[a-f0-9]{32}$/.test(path) && !['voice', 'realtime'].includes(mode))
              req.url = '/practice.html';
            next();
          });
        },
      },
    ],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': { target: backend },
        '/ws': { target: backend, ws: true },
        '/assets': { target: backend },
        '^/forum(?:\\.html)?(?:/|\\?|$)': { target: backend },
        '^/interview/[a-f0-9]{32}.*[?&]mode=(voice|realtime)(?:&|$)': { target: backend },
        '^/(account|catalog|roles|history|report|dashboard|guide)(/|\\?|$)': { target: backend },
      },
    },
  };
});
