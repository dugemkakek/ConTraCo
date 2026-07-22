"use client";

import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchSymbols, listVenues } from "@/lib/api";
import { useRouter } from "next/navigation";

type Props = {
  currentVenue?: string;
  onSelect?: (symbol: string, venue: string) => void;
};

export function SymbolSearch({ currentVenue = "gateio", onSelect }: Props) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Show all symbols when focused with empty query, filtered results when typing
  const { data, isLoading } = useQuery({
    queryKey: ["symbol-search", q || "__all__"],
    queryFn: () => searchSymbols(q || ""),
    enabled: open,
    staleTime: 30_000,
  });

  // Close on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
          inputRef.current && !inputRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const onSelectItem = (symbol: string, exchange: string) => {
    setOpen(false);
    setQ("");
    if (onSelect) {
      onSelect(symbol, exchange);
    } else {
      router.push(`/terminal/${symbol.replace("/", "-")}?venue=${exchange}`);
    }
  };

  return (
    <div className="relative">
      <input
        ref={inputRef}
        value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder="Search symbol..."
        className="bg-panel border border-border rounded px-2 py-1 text-sm w-44 focus:border-info outline-none text-primary placeholder:text-muted/60"
      />
      {open && (
        <div
          ref={dropdownRef}
          className="absolute top-full mt-1 left-0 w-64 bg-panel border border-border rounded shadow-lg z-50 max-h-72 overflow-auto"
        >
          {isLoading && (
            <p className="text-xs text-muted p-2">Loading...</p>
          )}
          {data && data.length === 0 && (
            <p className="text-xs text-muted p-2">No results</p>
          )}
          {data?.map((s) => (
            <button
              key={`${s.exchange}:${s.symbol}`}
              onClick={() => onSelectItem(s.symbol, s.exchange)}
              className="w-full text-left px-3 py-1.5 text-sm hover:bg-border/40 flex justify-between items-center"
            >
              <span className="text-primary">{s.symbol}</span>
              <span className="text-muted text-[10px] uppercase">{s.exchange}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}