"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth-context";
import { request } from "@/lib/api";

export default function AlertsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const { data: alerts } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => request<any[]>("/api/v1/alerts"),
    refetchInterval: 15_000,
    enabled: !!user,
  });

  const markRead = useMutation({
    mutationFn: (id: number) => request(`/api/v1/alerts/${id}/read`, { method: "PUT" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <main className="p-4 max-w-4xl mx-auto flex flex-col gap-4">
      <h1 className="text-lg font-semibold">Alerts</h1>

      {!alerts?.length && (
        <p className="text-muted text-sm">No alerts yet. Analysis runs will generate alerts for notable states.</p>
      )}

      <div className="flex flex-col gap-2">
        {alerts?.map((a) => (
          <div
            key={a.id}
            className={`bg-panel border rounded-md p-3 flex items-start gap-3 ${
              a.is_read ? "border-border" : "border-info/50"
            }`}
          >
            <div
              className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${
                a.severity === "CRITICAL" ? "bg-bearish" :
                a.severity === "WARNING" ? "bg-warning" : "bg-info"
              }`}
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-muted">
                  {new Date(a.created_at).toLocaleString()}
                </span>
                {!a.is_read && (
                  <button
                    onClick={() => markRead.mutate(a.id)}
                    className="text-[10px] text-info hover:underline"
                  >
                    Dismiss
                  </button>
                )}
              </div>
              <p className="text-sm text-primary mt-1">{a.message}</p>
              <span className="text-[10px] text-muted">{a.symbol}</span>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
