import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Static deploy on GitHub Pages and local `python -m http.server` both require
// relative asset URLs, so base must be './'.
// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    target: 'es2020',
    // Surface bundle weight in build output; budget is JS gzip < 300KB.
    reportCompressedSize: true,
  },
})
