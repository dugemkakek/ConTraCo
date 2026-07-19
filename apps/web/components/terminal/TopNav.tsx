"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/terminal/BTC-USDT", label: "Terminal" },
  { href: "/scan", label: "Scanner" },
  { href: "/analytics", label: "Analytics" },
  { href: "/alerts", label: "Alerts" },
  { href: "/journal", label: "Journal" },
  { href: "/settings", label: "Strategy" },
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
    <nav className="fixed top-0 inset-x-0 z-50 h-12 bg-panel border-b border-border flex items-center px-4 gap-4 text-xs">
      <Link href="/terminal/BTC-USDT" className="font-semibold text-primary">
        Confluence
      </Link>
      {mounted && !loading && user && !isAuthRoute && (
        <>
          <div className="flex items-center gap-2 text-muted">
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
