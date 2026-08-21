import path from "node:path";

import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // The dev overlay's badge sits in the bottom-left corner, on top of the
  // minimap. Compile errors still surface in the terminal and as the usual
  // full-screen overlay; this only removes the resting indicator.
  devIndicators: false,
  // Without this, Next walks up past the monorepo and picks whichever lockfile
  // it finds first in the home directory as the workspace root.
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
};

export default config;
