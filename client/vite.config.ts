/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import fs from 'fs'
import path from 'path'
import { execSync } from 'child_process'

// Get git branch name at build time
function getGitBranch(): string {
  try {
    return execSync('git branch --show-current', { encoding: 'utf-8' }).trim();
  } catch {
    return 'unknown';
  }
}

// Get git commit hash at build time
function getGitCommit(): string {
  try {
    return execSync('git rev-parse --short HEAD', { encoding: 'utf-8' }).trim();
  } catch {
    return 'unknown';
  }
}

const gitBranch = getGitBranch();
const gitCommit = getGitCommit();
const isDevelopmentBranch = gitBranch === 'development' || gitBranch === 'develop';

// Allow installer to override build type via env var (VITE_BUILD_TYPE=release)
const buildType = process.env.VITE_BUILD_TYPE || (isDevelopmentBranch ? 'dev' : 'release');

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // "pi" mode produces a stripped-down build for the BaluPi companion device
  const deviceMode = mode === 'pi' ? 'pi' : 'desktop';

  return {
  plugins: [react()],
  define: {
    '__BUILD_TYPE__': JSON.stringify(buildType),
    '__GIT_BRANCH__': JSON.stringify(gitBranch),
    '__GIT_COMMIT__': JSON.stringify(gitCommit),
    '__DEVICE_MODE__': JSON.stringify(deviceMode),
  },
  build: {
    outDir: deviceMode === 'pi' ? 'dist-pi' : 'dist',
    chunkSizeWarningLimit: deviceMode === 'pi' ? 300 : 600,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-charts': ['recharts'],
          'vendor-i18n': ['i18next', 'react-i18next', 'i18next-browser-languagedetector'],
          'vendor-icons': ['lucide-react'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/__tests__/setup.ts'],
    include: ['src/__tests__/**/*.test.{ts,tsx}'],
  },
  server: {
    host: '0.0.0.0',  // Expose to network
    allowedHosts: [
      'baluhost.local',
      'baluhost',
      '.local',  // Allow all .local domains
    ],
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
      '/openapi.json': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  };
})
