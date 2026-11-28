import type { NextConfig } from "next";

const apiUrl = process.env.API_URL ?? "http://localhost:8000";
// Sites allowed to embed the public forms in an iframe, e.g. "https://jstylehair.com".
// Empty (local development) allows any site.
const wordpressOrigin = process.env.WORDPRESS_ORIGIN ?? "";

// Content Security Policy for production builds. `next dev` needs eval for hot reload, so it
// only applies to `next build`. Turnstile (bot check on the public forms) loads from Cloudflare.
const isProd = process.env.NODE_ENV === "production";
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-src 'self' https://challenges.cloudflare.com",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

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
        headers: [
          {
            key: "Content-Security-Policy",
            value: `${isProd ? csp + "; " : ""}frame-ancestors 'self' ${wordpressOrigin || "*"}`,
          },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
      {
        // Everything except the public forms: never framed.
        source: "/((?!forms/bride|forms/planner).*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          ...(isProd ? [{ key: "Content-Security-Policy", value: `${csp}; frame-ancestors 'none'` }] : []),
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
};

export default nextConfig;
