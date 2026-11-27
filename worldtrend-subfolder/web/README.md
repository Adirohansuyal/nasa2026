# web — Blue Marble frontend

Vite + React + TypeScript. The globe, panels, chart and result card live here.

```bash
npm install
npm run dev        # http://localhost:5173
npm test           # vitest: data.ts + stats parity
npm run build
```

**Rule:** UI code gets data **only** from `src/data.ts`. It loads the published NASA MERRA-2 package from Cloudflare R2. Compact test fixtures live in `test-data/` and are not served to browsers. Map borders (Natural Earth) are in `public/boundaries/`.
See `../contract/README.md`.
