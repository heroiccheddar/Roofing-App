/**
 * Typed API client for StormLeads backend.
 *
 * Provides functions for all API endpoints with type-safe request/response handling.
 * Uses fetch API with automatic auth token injection and error handling.
 */

import type {
  AuthRegisterRequest,
  AuthLoginRequest,
  TokenResponse,
  AccountResponse,
  ServiceAreaUpdate,
  AlertPreferences,
  ZoneListParams,
  ZoneListResponse,
  ZoneDetailResponse,
  StormEventBrief,
  ZoneGeoJSONResponse,
  ZoneFeedbackCreate,
  ZoneFeedbackResponse,
  ZoneFeedbackListResponse,
  AlertHistoryResponse,
  CalibrationReport,
  WeightProposal,
  ModelDeployRequest,
  ModelDeployResponse,
  ErrorResponse,
} from '../types/api';

// ===== Configuration =====

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Token management — sessionStorage for persistence across HMR and page refresh
const TOKEN_KEY = 'stormleads_token';

let authToken: string | null = sessionStorage.getItem(TOKEN_KEY);

export function setAuthToken(token: string | null): void {
  authToken = token;
  if (token) {
    sessionStorage.setItem(TOKEN_KEY, token);
  } else {
    sessionStorage.removeItem(TOKEN_KEY);
  }
}

export function getAuthToken(): string | null {
  return authToken;
}

export function clearAuthToken(): void {
  authToken = null;
  sessionStorage.removeItem(TOKEN_KEY);
}

// ===== Generic Fetch Wrapper =====

interface ApiFetchOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { params, ...fetchOptions } = options;

  // Build URL with query params
  const url = new URL(path, API_BASE);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.append(key, String(value));
      }
    });
  }

  // Set default headers
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  // Merge existing headers
  if (fetchOptions.headers) {
    const existingHeaders = new Headers(fetchOptions.headers);
    existingHeaders.forEach((value, key) => {
      headers[key] = value;
    });
  }

  // Inject auth token if available
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  // Execute request
  const response = await fetch(url.toString(), {
    ...fetchOptions,
    headers,
  });

  // Handle errors
  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errorBody: ErrorResponse = await response.json();
      errorDetail = errorBody.detail || errorDetail;
    } catch {
      // Failed to parse error body, use default message
    }
    throw new Error(errorDetail);
  }

  // Parse and return response
  if (response.status === 204) {
    // No content
    return undefined as T;
  }

  return response.json();
}

// ===== Authentication =====

export async function register(
  data: AuthRegisterRequest
): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function login(
  email: string,
  password: string
): Promise<TokenResponse> {
  const data: AuthLoginRequest = { email, password };
  return apiFetch<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ===== Account Management =====

export async function getAccount(): Promise<AccountResponse> {
  return apiFetch<AccountResponse>('/api/v1/account');
}

export async function updateServiceArea(
  lat: number,
  lon: number,
  radiusKm: number
): Promise<AccountResponse> {
  const data: ServiceAreaUpdate = {
    lat,
    lon,
    radius_km: radiusKm,
  };
  return apiFetch<AccountResponse>('/api/v1/account/service-area', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function updateAlertPreferences(
  prefs: AlertPreferences
): Promise<AlertPreferences> {
  return apiFetch<AlertPreferences>('/api/v1/account/alert-preferences', {
    method: 'PUT',
    body: JSON.stringify(prefs),
  });
}

export async function getAlertPreferences(): Promise<AlertPreferences> {
  return apiFetch<AlertPreferences>('/api/v1/account/alert-preferences');
}

// ===== Lead Zones =====

export async function getZones(
  params?: ZoneListParams
): Promise<ZoneListResponse> {
  return apiFetch<ZoneListResponse>('/api/v1/zones', {
    params: params as Record<string, string | number | boolean | undefined>,
  });
}

export async function getZone(id: string): Promise<ZoneDetailResponse> {
  return apiFetch<ZoneDetailResponse>(`/api/v1/zones/${id}`);
}

export async function getZoneEvents(id: string): Promise<StormEventBrief[]> {
  return apiFetch<StormEventBrief[]>(`/api/v1/zones/${id}/events`);
}

export async function getZonesGeoJSON(
  bbox?: [number, number, number, number],
  minScore?: number,
  leadType?: string
): Promise<ZoneGeoJSONResponse> {
  const params: Record<string, string | number | undefined> = {};

  if (bbox) {
    params.bbox = bbox.join(',');
  }
  if (minScore !== undefined) {
    params.min_score = minScore;
  }
  if (leadType !== undefined) {
    params.lead_type = leadType;
  }

  return apiFetch<ZoneGeoJSONResponse>('/api/v1/zones/geojson', { params });
}

// ===== Zone Feedback =====

export async function submitFeedback(
  zoneId: string,
  data: ZoneFeedbackCreate
): Promise<ZoneFeedbackResponse> {
  return apiFetch<ZoneFeedbackResponse>(`/api/v1/zones/${zoneId}/feedback`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getFeedbackHistory(): Promise<ZoneFeedbackListResponse> {
  return apiFetch<ZoneFeedbackListResponse>('/api/v1/feedback/my-history');
}

// ===== Alerts =====

export async function getAlertHistory(): Promise<AlertHistoryResponse> {
  return apiFetch<AlertHistoryResponse>('/api/v1/alerts/history');
}

/**
 * Connect to WebSocket alert stream.
 * Returns WebSocket instance that streams real-time zone alerts.
 */
export function connectAlertStream(): WebSocket {
  const wsUrl = API_BASE.replace(/^http/, 'ws') + '/api/v1/alerts/stream';
  const ws = new WebSocket(wsUrl);

  // Inject auth token on connection
  ws.addEventListener('open', () => {
    if (authToken) {
      ws.send(JSON.stringify({ type: 'auth', token: authToken }));
    }
  });

  return ws;
}

// ===== Internal Admin =====

export async function getCalibrationReport(): Promise<CalibrationReport> {
  return apiFetch<CalibrationReport>('/api/v1/internal/calibration/report');
}

export async function proposeWeights(): Promise<WeightProposal> {
  return apiFetch<WeightProposal>('/api/v1/internal/model/propose-weights', {
    method: 'POST',
  });
}

export async function deployModel(
  request: ModelDeployRequest
): Promise<ModelDeployResponse> {
  return apiFetch<ModelDeployResponse>('/api/v1/internal/model/deploy', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

// ===== Helper Types =====

export type { ErrorResponse };
