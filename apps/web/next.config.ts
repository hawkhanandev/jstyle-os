import type { NextConfig } from "next";

const apiUrl = process.env.API_URL ?? "http://localhost:8000";
// Sites allowed to embed the public forms in an iframe, e.g. "https://jstylehair.com".
// Empty (local development) allows any site.
const wordpressOrigin = process.env.WORDPRESS_ORIGIN ?? "";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    // The browser only talks to this app; /api is proxied to FastAPI so cookies stay first-party.
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/forms/:kind(bride|planner)",
        headers: [{ key: "Content-Security-Policy", value: `frame-ancestors 'self' ${wordpressOrigin || "*"}` }],
      },
      {
        // Everything except the public forms: never framed.
        source: "/((?!forms/bride|forms/planner).*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
};

export default nextConfig;
