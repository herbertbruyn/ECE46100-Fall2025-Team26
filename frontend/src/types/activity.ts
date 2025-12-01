export interface ActivityLog {
  id: number;
  user: string;
  action: 'upload' | 'update' | 'delete' | 'download' | 'login' | 'logout' | 'search' | 'view' | 'rate';
  artifact_type?: 'model' | 'dataset' | 'code';
  artifact_id?: number;
  artifact_name?: string;
  details?: string;
  ip_address?: string;
  timestamp: string;
}

export interface ActivityFilters {
  user?: string;
  action?: string;
  artifact_type?: string;
  dateFrom?: string;
  dateTo?: string;
}