import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'

function previewFileFor(root: string, url: string): string {
  return path.join(root, 'public', url.replace('/data/', 'preview-data/'))
}

function previewDataPlugin(): Plugin {
  return {
    name: 'preview-data',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url?.split('?')[0] ?? ''
        const file = previewFileFor(server.config.root, url)
        const preview =
          url === '/data/problems-index.json'
          || url === '/data/meta.json'
          || url.startsWith('/data/players/')
          || url.startsWith('/data/skill-leaderboards/')
          || (url.startsWith('/data/contests/') && fs.existsSync(file))
        if (!preview || !fs.existsSync(file)) {
          next()
          return
        }
        res.setHeader('Content-Type', 'application/json; charset=utf-8')
        res.setHeader('Cache-Control', 'no-store')
        fs.createReadStream(file).pipe(res)
      })
    },
  }
}

export default defineConfig({
  base: './',
  plugins: [react(), previewDataPlugin()],
  build: {
    target: 'es2020',
    reportCompressedSize: true,
  },
})
