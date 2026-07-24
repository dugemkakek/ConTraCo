"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";

const NAV = [
  { href: "/mission-control", label: "Mission Control" },
  { href: "/charting", label: "Charting" },
  { href: "/debate", label: "Debate Chamber" },
  { href: "/trenches", label: "Trenches" },
  { href: "/token-safety", label: "Token Safety" },
  { href: "/strategy", label: "Strategy Lab" },
  { href: "/journal", label: "Journal" },
  { href: "/arbitrage", label: "Arbitrage" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/wallet", label: "Wallet" },
  { href: "/settings", label: "Settings" },
];

const NAV_MORE = [
  { href: "/terminal/BTC-USDT", label: "Terminal" },
  { href: "/scan", label: "Scanner" },
  { href: "/analytics", label: "Analytics" },
  { href: "/alerts", label: "Alerts" },
  { href: "/whales", label: "Whales" },
];

export function TopNav() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  async function onLogout() {
    await logout();
    router.push("/login");
  }

  const isAuthRoute = pathname?.startsWith("/login") || pathname?.startsWith("/register");

  return (
    <nav className="fixed top-0 inset-x-0 z-50 h-11 bg-panel/95 backdrop-blur border-b border-border flex items-center px-3 gap-4 text-xs">
      <Link href="/mission-control" className="flex items-center gap-2 font-mono font-semibold tracking-tight text-primary">
        <span className="brand-mark">C</span>
        CONFLUENCE
      </Link>
      {mounted && !loading && user && !isAuthRoute && (
        <>
          <div className="flex items-center gap-1 text-muted">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`px-2 py-1 rounded ${
                  pathname === item.href || pathname?.startsWith(item.href + "/")
                    ? "bg-info/20 text-info"
                    : "hover:text-primary"
                }`}
              >
                {item.label}
              </Link>
            ))}
            <span className="w-px h-4 bg-border mx-1" />
            {NAV_MORE.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`px-1.5 py-1 rounded text-[10px] ${
                  pathname?.startsWith(item.href.split("/")[0] + "/") || pathname === item.href
                    ? "bg-info/20 text-info"
                    : "hover:text-primary"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-3">
            <span className="text-muted">{user.email}</span>
            <button
              onClick={onLogout}
              className="px-2 py-1 rounded border border-border hover:border-bearish hover:text-bearish"
            >
              Logout
            </button>
          </div>
        </>
      )}
    </nav>
  );
}
