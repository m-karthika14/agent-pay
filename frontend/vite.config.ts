import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// AgentPay frontend build config. Tailwind is wired in via its official Vite
// plugin (Tailwind v4 style — no separate tailwind.config.js/postcss needed).
// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
})
