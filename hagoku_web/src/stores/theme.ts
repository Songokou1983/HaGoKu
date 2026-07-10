import { create } from "zustand";

export type ThemeId = "dark" | "light";

interface ThemeStore {
  theme: ThemeId;
  setTheme: (t: ThemeId) => void;
}

export const useThemeStore = create<ThemeStore>((set, get) => ({
  theme: (localStorage.getItem("hagoku_theme") as ThemeId) || "dark",
  setTheme: (t) => {
    localStorage.setItem("hagoku_theme", t);
    set({ theme: t });
  },
}));
