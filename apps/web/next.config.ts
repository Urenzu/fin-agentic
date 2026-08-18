import path from "node:path";

import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Without this, Next walks up past the monorepo and picks whichever lockfile
  // it finds first in the home directory as the workspace root.
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
};

export default config;
