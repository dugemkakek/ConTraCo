"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";

export default function Home() {
  const { user, loading, refresh } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (user) router.replace("/terminal/BTC-USDT");
    else router.replace("/login");
  }, [user, loading, router]);

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-4 p-6">
      <h1 className="text-2xl font-semibold">Confluence Trading Consultant</h1>
      <p className="text-muted text-sm text-center max-w-md">
        Decision support only — human approval required. Not financial advice.
      </p>
      <Link
        href="/terminal/BTC-USDT"
        onClick={(e) => {
          e.preventDefault();
          refresh();
        }}
        className="mt-4 px-4 py-2 rounded-md bg-info/20 border border-info text-info hover:bg-info/30 transition"
      >
        Continue
      </Link>
    </main>
  );
}
