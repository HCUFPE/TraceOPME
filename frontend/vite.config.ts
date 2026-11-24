import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { fileURLToPath } from 'url'
import tailwindcss from '@tailwindcss/vite'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// https://vitejs.dev/config/
export default defineConfig({
  base: '/',
  plugins: [
    // whitespace 'preserve': o espaço entre elementos em linhas diferentes vale como
    // no HTML comum (as telas foram portadas dos templates da v17).
    vue({ template: { compilerOptions: { whitespace: 'preserve' } } }),
    tailwindcss(),
  ],
  build: {
    outDir: path.resolve(__dirname, '../src/static/dist'),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    }
  }
})
