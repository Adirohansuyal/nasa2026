/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** URL of the published NASA MERRA-2 data package. */
  readonly VITE_DATA_URL?: string;
  /** Optional separate URL for Point-mode tiles. */
  readonly VITE_TILES_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
