import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  publicDir: 'C:/Users/28479/Documents/Codex/2026-09-05/https-github-com-hei-maom-xcpcrating/outputs/skill-preview-root',
  server: { host: '127.0.0.1', port: 5174 },
  plugins: [react()],
})
