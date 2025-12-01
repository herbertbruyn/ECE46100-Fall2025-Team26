import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import type { 
  Artifact, 
  UploadResponse, 
  SearchQuery, 
  RegexSearchQuery, 
  CostResult, 
  HealthStatus,
  AuthToken 
} from '../types';
import type { ActivityLog } from '../types/activity';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class ApiService {
  private api: AxiosInstance;

  constructor() {
    this.api = axios.create({
      baseURL: API_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
      const token = localStorage.getItem('token');
      if (token && config.headers) {
        config.headers.Authorization = `Token ${token}`;
      }
      return config;
    });
  }

  async login(username: string, password: string, is_admin: boolean = false): Promise<AuthToken> {
    const { data } = await this.api.post<AuthToken>('/authenticate', {
      username,
      password,
      is_admin,
    });
    localStorage.setItem('token', data.token);
    localStorage.setItem('user', JSON.stringify(data.user));
    return data;
  }

  logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
  }

  getCurrentUser() {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
  }

  async getArtifacts(): Promise<Artifact[]> {
    const { data } = await this.api.get<Artifact[]>('/artifacts');
    return data;
  }

  async getArtifact(id: number): Promise<Artifact> {
    const { data } = await this.api.get<Artifact>(`/artifact/${id}`);
    return data;
  }

  async uploadArtifact(url: string, type: string): Promise<UploadResponse> {
    const { data } = await this.api.post<UploadResponse>('/artifact', {
      url,
      type,
    });
    return data;
  }

  async updateArtifact(id: number, updates: Partial<Artifact>): Promise<Artifact> {
    const { data } = await this.api.put<Artifact>(`/artifact/${id}`, updates);
    return data;
  }

  async deleteArtifact(id: number): Promise<void> {
    await this.api.delete(`/artifact/${id}`);
  }

  async downloadArtifact(id: number): Promise<Blob> {
    const { data } = await this.api.get(`/artifact/${id}/download`, {
      responseType: 'blob',
    });
    return data;
  }

  async searchArtifacts(query: SearchQuery): Promise<Artifact[]> {
    const { data } = await this.api.post<Artifact[]>('/artifacts/search', query);
    return data;
  }

  async searchByRegex(query: RegexSearchQuery): Promise<Artifact[]> {
    const { data } = await this.api.post<Artifact[]>('/artifacts/by_regex', query);
    return data;
  }

  async resetArtifacts(): Promise<{ message: string }> {
    const { data } = await this.api.post('/reset');
    return data;
  }

  async calculateCost(): Promise<CostResult> {
    const { data } = await this.api.get<CostResult>('/cost');
    return data;
  }

  async checkHealth(): Promise<HealthStatus> {
    const { data } = await this.api.get<HealthStatus>('/health');
    return data;
  }

  async getActivityLog(filters?: {
    user?: string;
    action?: string;
    artifact_type?: string;
    date_from?: string;
    date_to?: string;
  }): Promise<ActivityLog[]> {
    const params = new URLSearchParams();
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value.toString());
      });
    }
    
    try {
      const { data } = await this.api.get(`/activity?${params.toString()}`);
      return data.results || data;
    } catch (error) {
      console.warn('Activity log endpoint not available:', error);
      return [];
    }
  }
}

export const api = new ApiService();
export default api;
