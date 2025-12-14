export type ArtifactType = 'model' | 'dataset' | 'code';

export interface User {
  name: string;
  is_admin: boolean;
}

export interface AuthToken {
  token: string;
  user: User;
}

export interface Artifact {
  id: number;
  name: string;
  type: ArtifactType;
  source_url: string;
  version?: string;
  sha256?: string;
  size_bytes?: number;
  status: 'pending' | 'rating' | 'completed' | 'failed' | 'rejected';
  status_message?: string;
  created_at: string;
  updated_at: string;
  rating_completed_at?: string;
  uploaded_by?: string;
  dataset_name?: string;
  code_name?: string;
  dataset_id?: number;
  code_id?: number;
  blob?: string;
}

export interface ModelRating {
  net_score: number;
  net_score_latency: number;
  ramp_up_time: number;
  ramp_up_time_latency: number;
  bus_factor: number;
  bus_factor_latency: number;
  performance_claims: number;
  performance_claims_latency: number;
  license: number;
  license_latency: number;
  dataset_and_code_score: number;
  dataset_and_code_score_latency: number;
  dataset_quality: number;
  dataset_quality_latency: number;
  code_quality: number;
  code_quality_latency: number;
  reproducibility: number;
  reproducibility_latency: number;
  reviewedness: number;
  reviewedness_latency: number;
  tree_score: number;
  tree_score_latency: number;
  size_score: number;
  size_score_latency: number;
  total_rating_time: number;
}

export interface UploadResponse {
  metadata: Artifact;
  data: {
    url: string;
    download_url?: string;
  };
  scores?: ModelRating;
  status: string;
}

export interface SearchQuery {
  name?: string;
  version?: string;
}

export interface RegexSearchQuery {
  regex: string;
}

export interface CostResult {
  [key: string]: {
    standby: number;
    total_cost: number;
  };
}

export interface HealthStatus {
  status: 'ok' | 'degraded' | 'down';
  components?: {
    database?: string;
    storage?: string;
  };
}