import type { NextConfig } from 'next'

const config: NextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_APP_VERSION: process.env.npm_package_version ?? '0.25.0',
  },
}

export default config
