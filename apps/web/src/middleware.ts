import { NextResponse, type NextRequest } from "next/server";

// Cheap gate: no session cookie means straight to sign-in. The API still checks the session.
export function middleware(req: NextRequest) {
  if (!req.cookies.get("jstyle_session")) {
    const url = req.nextUrl.clone();
    url.pathname = "/sign-in";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|sign-in|forms/bride|forms/planner|_next|favicon.ico).*)"],
};
