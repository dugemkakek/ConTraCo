"use client";

import { useQuery } from "@tanstack/react-query";
import { listVenues } from "@/lib/api";

type Props = {
  value: string;
  onChange: (v: string) => void;
};

export function VenueSelector({ value, onChange }: Props) {
  const { data } = useQuery({
    queryKey: ["venues"],
    queryFn: listVenues,
    staleTime: 300_000,
  });

  // Filter to live-data exchanges only — never show mock.
  const venues = (data ?? []).filter((v) => v.id !== "mock");
  return (
    <select
      value={venues.some((v) => v.id === value) ? value : venues[0]?.id ?? "binance"}
      onChange={(e) => onChange(e.target.value)}
      className="bg-border/40 border border-border rounded px-2 py-1 text-xs outline-none focus:border-info text-primary"
    >
      {venues.map((v) => (
        <option key={v.id} value={v.id}>
          {v.label}
        </option>
      ))}
    </select>
  );
}
