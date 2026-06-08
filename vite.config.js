import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: '.',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        signup: resolve(__dirname, 'signup.html'),
        login: resolve(__dirname, 'login.html'),
        dashboard: resolve(__dirname, 'dashboard.html'),
        admin: resolve(__dirname, 'admin.html'),
        forgot: resolve(__dirname, 'forgot.html'),
        'reset-password': resolve(__dirname, 'reset-password.html'),
        termos: resolve(__dirname, 'termos.html'),
        privacidade: resolve(__dirname, 'privacidade.html'),
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:5000',
    },
  },
});
