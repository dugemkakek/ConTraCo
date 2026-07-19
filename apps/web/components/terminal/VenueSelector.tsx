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

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-border/40 border border-border rounded px-2 py-1 text-xs outline-none focus:border-info text-primary"
    >
      {data?.map((v) => (
        <option key={v.id} value={v.id}>
          {v.label}
        </option>
      ))}
    </select>
  );
}
