import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import fs from 'fs'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',  // Expose to network
    https: (() => {
      const keyPath = path.resolve(__dirname, '../dev-certs/key.pem')
      const certPath = path.resolve(__dirname, '../dev-certs/cert.pem')
      if (fs.existsSync(keyPath) && fs.existsSync(certPath)) {
        return { key: keyPath, cert: certPath }
      }
      return undefined
    })(),
    proxy: {
      '/api': {
        target: 'http://localhost:8000',  // Backend runs on HTTP in dev mode
        changeOrigin: true,
        secure: false,
        ws: true,
        configure: (proxy, _options) => {
          proxy.on('error', (err, _req, _res) => {
            console.log('proxy error', err);
          });
          proxy.on('proxyReq', (_proxyReq, req, _res) => {
            console.log('Sending Request to Target:', req.method, req.url);
            console.log('Authorization header:', req.headers.authorization ? 'Present' : 'Missing');
          });
          proxy.on('proxyRes', (proxyRes, req, _res) => {
            console.log('Received Response from Target:', proxyRes.statusCode, req.url);
          });
        },
      },
    },
  },
})
