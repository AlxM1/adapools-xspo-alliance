import { create } from "zustand";
import { persist } from "zustand/middleware";
import { authApi, User } from "@/lib/api";

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  fetchUser: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (email: string, password: string) => {
        set({ isLoading: true, error: null });
        try {
          const data = await authApi.login(email, password);
          localStorage.setItem("access_token", data.access_token);
          localStorage.setItem("refresh_token", data.refresh_token);

          const user = await authApi.getProfile();
          set({ user, isAuthenticated: true, isLoading: false });
        } catch (error: any) {
          const message = error.response?.data?.detail || "Login failed";
          set({ error: message, isLoading: false });
          throw new Error(message);
        }
      },

      register: async (email: string, username: string, password: string) => {
        set({ isLoading: true, error: null });
        try {
          await authApi.register(email, username, password);
          // Auto-login after registration
          await get().login(email, password);
        } catch (error: any) {
          const message = error.response?.data?.detail || "Registration failed";
          set({ error: message, isLoading: false });
          throw new Error(message);
        }
      },

      logout: async () => {
        set({ isLoading: true });
        try {
          await authApi.logout();
        } catch (error) {
          // Ignore logout errors
        } finally {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          set({ user: null, isAuthenticated: false, isLoading: false });
        }
      },

      fetchUser: async () => {
        const token = localStorage.getItem("access_token");
        if (!token) {
          set({ isAuthenticated: false, user: null });
          return;
        }

        set({ isLoading: true });
        try {
          const user = await authApi.getProfile();
          set({ user, isAuthenticated: true, isLoading: false });
        } catch (error) {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          set({ user: null, isAuthenticated: false, isLoading: false });
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({ isAuthenticated: state.isAuthenticated }),
    }
  )
);
