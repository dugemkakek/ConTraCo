import { create } from "zustand";
import type { RunOut } from "@/lib/api";

interface AnalysisStore {
  autoAnalyze: boolean;
  setAutoAnalyze: (v: boolean) => void;
  currentRun: RunOut | null;
  setCurrentRun: (run: RunOut | null) => void;
  isAnalyzing: boolean;
  setIsAnalyzing: (v: boolean) => void;
}

export const useAnalysisStore = create<AnalysisStore>((set) => ({
  autoAnalyze: false,
  setAutoAnalyze: (v) => set({ autoAnalyze: v }),
  currentRun: null,
  setCurrentRun: (run) => set({ currentRun: run }),
  isAnalyzing: false,
  setIsAnalyzing: (v) => set({ isAnalyzing: v }),
}));
