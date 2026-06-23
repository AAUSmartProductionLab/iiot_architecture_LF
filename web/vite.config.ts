import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// usePolling makes HMR work over Docker bind mounts (esp. Windows/WSL2), where
// native filesystem events from the host don't reach the container.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    watch: { usePolling: true },
  },
});
