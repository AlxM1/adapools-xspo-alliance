import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Create axios instance
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for token refresh
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && originalRequest) {
      const refreshToken = typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;

      if (refreshToken) {
        try {
          const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          });

          const { access_token, refresh_token: newRefreshToken } = response.data;
          localStorage.setItem("access_token", access_token);
          localStorage.setItem("refresh_token", newRefreshToken);

          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${access_token}`;
          }
          return api(originalRequest);
        } catch (refreshError) {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          window.location.href = "/login";
        }
      }
    }

    return Promise.reject(error);
  }
);

// Types
export interface User {
  id: string;
  email: string;
  username: string;
  role: "user" | "admin" | "super_admin";
  is_active: boolean;
  created_at: string;
}

export interface Voice {
  id: string;
  name: string;
  language: string;
  is_default: boolean;
  sample_url?: string;
  created_at: string;
}

export interface Avatar {
  id: string;
  name: string;
  is_default: boolean;
  thumbnail_url?: string;
  created_at: string;
}

export interface PipelineJob {
  id: string;
  newsletter_title: string;
  status: "pending" | "processing" | "completed" | "failed";
  progress: number;
  current_stage?: string;
  created_at: string;
  completed_at?: string;
  error_message?: string;
}

export interface Video {
  id: string;
  title: string;
  duration_sec: number;
  file_size: number;
  format: string;
  thumbnail_url?: string;
  video_url: string;
  created_at: string;
}

export interface Publication {
  id: string;
  platform: string;
  status: "pending" | "scheduled" | "published" | "failed";
  published_url?: string;
  scheduled_at?: string;
  published_at?: string;
  error_message?: string;
}

export interface SocialConnection {
  id: string;
  platform: string;
  is_connected: boolean;
  username?: string;
  expires_at?: string;
}

export interface DashboardStats {
  total_pipelines: number;
  completed_pipelines: number;
  total_videos: number;
  total_publications: number;
  video_minutes_generated: number;
  storage_used_mb: number;
}

// Auth API
export const authApi = {
  login: async (email: string, password: string) => {
    const formData = new URLSearchParams();
    formData.append("username", email);
    formData.append("password", password);

    const response = await api.post("/auth/login", formData, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    return response.data;
  },

  register: async (email: string, username: string, password: string) => {
    const response = await api.post("/auth/register", { email, username, password });
    return response.data;
  },

  logout: async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    await api.post("/auth/logout", { refresh_token: refreshToken });
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  },

  getProfile: async (): Promise<User> => {
    const response = await api.get("/auth/me");
    return response.data;
  },

  updateProfile: async (data: Partial<User>) => {
    const response = await api.put("/auth/me", data);
    return response.data;
  },
};

// Pipeline API
export const pipelineApi = {
  create: async (data: {
    newsletter_content: string;
    newsletter_title: string;
    generate_long_form?: boolean;
    generate_shorts?: boolean;
    shorts_count?: number;
    voice_id?: string;
    avatar_id?: string;
    target_platforms?: string[];
    auto_publish?: boolean;
  }): Promise<PipelineJob> => {
    const response = await api.post("/pipeline", data);
    return response.data;
  },

  list: async (params?: {
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ items: PipelineJob[]; total: number }> => {
    const response = await api.get("/pipeline", { params });
    return response.data;
  },

  get: async (id: string): Promise<PipelineJob & { stages: any[]; videos: Video[] }> => {
    const response = await api.get(`/pipeline/${id}`);
    return response.data;
  },

  cancel: async (id: string) => {
    const response = await api.post(`/pipeline/${id}/cancel`);
    return response.data;
  },

  retry: async (id: string) => {
    const response = await api.post(`/pipeline/${id}/retry`);
    return response.data;
  },
};

// Voice API
export const voiceApi = {
  list: async (): Promise<{ items: Voice[]; total_count: number }> => {
    const response = await api.get("/voices");
    return response.data;
  },

  create: async (formData: FormData): Promise<Voice> => {
    const response = await api.post("/voices/clone", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return response.data;
  },

  delete: async (id: string) => {
    await api.delete(`/voices/${id}`);
  },

  setDefault: async (id: string) => {
    const response = await api.post(`/voices/${id}/set-default`);
    return response.data;
  },
};

// Avatar API
export const avatarApi = {
  list: async (): Promise<{ items: Avatar[]; total_count: number }> => {
    const response = await api.get("/avatars");
    return response.data;
  },

  create: async (formData: FormData): Promise<Avatar> => {
    const response = await api.post("/avatars/create", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return response.data;
  },

  delete: async (id: string) => {
    await api.delete(`/avatars/${id}`);
  },

  setDefault: async (id: string) => {
    const response = await api.post(`/avatars/${id}/set-default`);
    return response.data;
  },
};

// Social API
export const socialApi = {
  getConnections: async (): Promise<SocialConnection[]> => {
    const response = await api.get("/platforms");
    return response.data;
  },

  getAuthUrl: async (platform: string): Promise<{ auth_url: string }> => {
    const response = await api.get(`/auth/${platform}`);
    return response.data;
  },

  disconnect: async (platform: string) => {
    await api.delete(`/auth/${platform}`);
  },
};

// Video API
export const videoApi = {
  list: async (params?: {
    pipeline_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ items: Video[]; total: number }> => {
    const response = await api.get("/videos", { params });
    return response.data;
  },

  get: async (id: string): Promise<Video & { publications: Publication[] }> => {
    const response = await api.get(`/videos/${id}`);
    return response.data;
  },

  publish: async (id: string, platforms: string[], schedule?: string) => {
    const response = await api.post(`/videos/${id}/publish`, {
      platforms,
      scheduled_at: schedule,
    });
    return response.data;
  },

  download: async (id: string): Promise<Blob> => {
    const response = await api.get(`/videos/${id}/download`, {
      responseType: "blob",
    });
    return response.data;
  },
};

// Dashboard API
export const dashboardApi = {
  getStats: async (): Promise<DashboardStats> => {
    const response = await api.get("/dashboard/stats");
    return response.data;
  },

  getRecentPipelines: async (): Promise<PipelineJob[]> => {
    const response = await api.get("/dashboard/recent-pipelines");
    return response.data;
  },

  getRecentVideos: async (): Promise<Video[]> => {
    const response = await api.get("/dashboard/recent-videos");
    return response.data;
  },
};

// Health API
export const healthApi = {
  check: async () => {
    const response = await api.get("/health");
    return response.data;
  },
};

export default api;
