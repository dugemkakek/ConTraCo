"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth-context";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (user) router.replace("/mission-control");
    else router.replace("/login");
  }, [user, loading, router]);

  return (
    <main className="min-h-screen flex items-center justify-center bg-bg">
      <div className="w-6 h-6 border-2 border-info border-t-transparent rounded-full animate-spin" />
    </main>
  );
}
