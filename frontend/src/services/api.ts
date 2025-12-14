import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import type {
  Artifact,
  ArtifactType,
  ModelRating,
  UploadResponse,
  SearchQuery,
  RegexSearchQuery,
  CostResult,
  HealthStatus,
  AuthToken,
} from '../types';
import type { ActivityLog } from '../types/activity';

const API_URL =
  (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';

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
    // Backend expects this format (see auth_views.py)
    const { data } = await this.api.put<string>('/authenticate', {
      user: {
        name: username,
        is_admin: is_admin,
      },
      secret: {
        password: password,
      },
    });

    // Backend returns just the token string
    const token = data;
    const user = { name: username, is_admin: is_admin };

    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));

    return { token, user };
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
    // Backend expects POST /artifacts with query array
    // Use wildcard to get all artifacts
    const { data } = await this.api.post<Artifact[]>('/artifacts', [{ name: '*' }]);
    return data;
  }

  async getArtifact(type: ArtifactType, id: number): Promise<Artifact> {
    const { data } = await this.api.get<Artifact>(`/artifacts/${type}/${id}`);
    return data;
  }

  async uploadArtifact(type: ArtifactType, url: string, revision?: string): Promise<UploadResponse> {
    const payload: any = { url };
    if (revision) {
      payload.revision = revision;
    }
    const { data } = await this.api.post<UploadResponse>(`/artifact/${type}`, payload);
    return data;
  }

  async updateArtifact(id: number, updates: Partial<Artifact>): Promise<Artifact> {
    const { data } = await this.api.put<Artifact>(`/artifact/${id}`, updates);
    return data;
  }

  async deleteArtifact(type: ArtifactType, id: number): Promise<void> {
    await this.api.delete(`/artifacts/${type}/${id}`);
  }

  async downloadArtifact(id: number): Promise<Blob> {
    const { data } = await this.api.get(`/artifact/${id}/download`, {
      responseType: 'blob',
    });
    return data;
  }

  async searchArtifacts(query: SearchQuery): Promise<Artifact[]> {
    const { data } = await this.api.post<Artifact[]>('/artifacts', [query]);
    return data;
  }

  async searchByRegex(query: RegexSearchQuery): Promise<Artifact[]> {
    const { data } = await this.api.post<Artifact[]>('/artifact/byRegEx', query);
    return data;
  }

  async resetArtifacts(): Promise<{ message: string }> {
    const { data } = await this.api.delete('/reset');
    return data;
  }

    async resetRegistry(): Promise<{ message: string }> {
    // alias used by AdminPage
    return this.resetArtifacts();
  }

  async calculateCost(type: ArtifactType, id: number, includeDependencies: boolean = true): Promise<CostResult> {
    const { data } = await this.api.get<CostResult>(`/artifact/${type}/${id}/cost?dependency=${includeDependencies}`);
    return data;
  }

  async getModelRating(id: number): Promise<ModelRating> {
    const { data } = await this.api.get<ModelRating>(`/artifact/model/${id}/rate`);
    return data;
  }

  getDownloadUrl(artifact: Artifact): string | null {
    if (!artifact.blob) return null;
    // The blob field contains the relative URL from Django
    return `${API_URL}${artifact.blob}`;
  }

  async checkHealth(): Promise<HealthStatus> {
    const { data } = await this.api.get<HealthStatus>('/health');
    return data;
  }
    async getHealth(): Promise<HealthStatus> {
    return this.checkHealth();
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

    const { data } = await this.api.get(`/activity?${params.toString()}`);
    return data.results || data;
  }

  async getArtifactLineage(id: number): Promise<{ nodes: any[]; edges: any[] }> {
    const { data } = await this.api.get(`/artifact/model/${id}/lineage`);
    return data;
  }

  async checkLicenseCompatibility(modelId: number, githubUrl: string): Promise<boolean> {
    const { data } = await this.api.post(`/artifact/model/${modelId}/license-check`, {
      github_url: githubUrl
    });
    return data;
  }
}


export const api = new ApiService();
export default api;
