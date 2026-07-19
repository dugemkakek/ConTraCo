"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      router.push("/terminal/BTC-USDT");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <form
        onSubmit={onSubmit}
        className="bg-panel border border-border rounded-lg p-6 w-full max-w-sm flex flex-col gap-4"
      >
        <header>
          <h1 className="text-lg font-semibold">Sign in</h1>
          <p className="text-xs text-muted mt-1">
            Decision support only — human approval required.
          </p>
        </header>
        <label className="flex flex-col gap-1 text-xs text-muted">
          Email
          <input
            type="email"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="bg-bg border border-border rounded px-2 py-1 text-primary"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted">
          Password
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="bg-bg border border-border rounded px-2 py-1 text-primary"
          />
        </label>
        {error && (
          <div data-testid="login-error" className="text-bearish text-xs">{error}</div>
        )}
        <button
          type="submit"
          disabled={busy}
          className="bg-info/20 border border-info text-info rounded px-3 py-2 text-sm hover:bg-info/30 disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="text-xs text-muted">
          New here?{" "}
          <Link href="/register" className="text-info">
            Create an account
          </Link>
        </p>
      </form>
    </main>
  );
}
