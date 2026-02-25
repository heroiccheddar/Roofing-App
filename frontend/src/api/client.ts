/**
 * Typed API client for RoofIQ backend.
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
  TractGeoJSONResponse,
  ZoneFeedbackCreate,
  ZoneFeedbackResponse,
  ZoneFeedbackListResponse,
  CanvassSessionCreate,
  CanvassSessionUpdate,
  CanvassSessionResponse,
  CanvassSessionListResponse,
  AlertHistoryResponse,
  CalibrationReport,
  WeightProposal,
  ModelDeployRequest,
  ModelDeployResponse,
  ErrorResponse,
  RecommendationResponse,
  RouteRequest,
  RouteResponse,
  PropertyListResponse,
  LeadPinCreate,
  LeadPinUpdate,
  LeadPinResponse,
  LeadPinListResponse,
  PinActivityListResponse,
} from '../types/api';

// ===== Configuration =====

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Token management — sessionStorage for persistence across HMR and page refresh
const TOKEN_KEY = 'roofiq_token';

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
    // Expired or invalid token — log out and redirect to login
    if (response.status === 401) {
      clearAuthToken();
      window.location.href = '/login';
      throw new Error('Session expired. Please log in again.');
    }

    let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errorBody = await response.json();
      // FastAPI validation errors return detail as an array
      if (typeof errorBody.detail === 'string') {
        errorDetail = errorBody.detail;
      } else if (Array.isArray(errorBody.detail)) {
        errorDetail = errorBody.detail.map((e: any) => e.msg || String(e)).join('; ');
      } else if (errorBody.detail) {
        errorDetail = String(errorBody.detail);
      }
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
  return apiFetch<AccountResponse>('/api/v1/account/profile');
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

export async function getZoneTracts(
  zoneId: string
): Promise<TractGeoJSONResponse> {
  return apiFetch<TractGeoJSONResponse>(`/api/v1/zones/${zoneId}/tracts`);
}

// ===== Tract Properties =====

export async function getTractProperties(
  zoneId: string,
  tractGeoid: string,
): Promise<PropertyListResponse> {
  return apiFetch<PropertyListResponse>(
    `/api/v1/zones/${zoneId}/tracts/${tractGeoid}/properties`,
  );
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

// ===== Canvass Sessions =====

export async function startCanvassSession(
  zoneId: string,
  data?: CanvassSessionCreate
): Promise<CanvassSessionResponse> {
  return apiFetch<CanvassSessionResponse>(`/api/v1/zones/${zoneId}/canvass`, {
    method: 'POST',
    body: JSON.stringify(data || {}),
  });
}

export async function updateCanvassSession(
  sessionId: string,
  data: CanvassSessionUpdate
): Promise<CanvassSessionResponse> {
  return apiFetch<CanvassSessionResponse>(`/api/v1/canvass/${sessionId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function getZoneCanvassHistory(
  zoneId: string
): Promise<CanvassSessionListResponse> {
  return apiFetch<CanvassSessionListResponse>(`/api/v1/zones/${zoneId}/canvass`);
}

export async function getMyCanvassHistory(): Promise<CanvassSessionListResponse> {
  return apiFetch<CanvassSessionListResponse>('/api/v1/canvass/my-history');
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

// ===== Recommendations =====

export async function getRecommendations(
  lat: number,
  lon: number,
  limit: number = 5,
  stormOnly: boolean = false,
): Promise<RecommendationResponse> {
  return apiFetch<RecommendationResponse>('/api/v1/recommendations', {
    params: { lat, lon, limit, storm_only: stormOnly },
  })
}

// ===== Route Planning =====

export async function planRoute(
  request: RouteRequest,
): Promise<RouteResponse> {
  return apiFetch<RouteResponse>('/api/v1/route', {
    method: 'POST',
    body: JSON.stringify(request),
  })
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

// ===== Lead Pins =====

export async function getLeadPins(
  bbox?: [number, number, number, number],
): Promise<LeadPinListResponse> {
  const params: Record<string, string | undefined> = {};
  if (bbox) params.bbox = bbox.join(',');
  return apiFetch<LeadPinListResponse>('/api/v1/leads', { params });
}

export async function getLeadPinsGeoJSON(
  bbox?: [number, number, number, number],
  disposition?: string,
): Promise<any> {
  const params: Record<string, string | undefined> = {};
  if (bbox) params.bbox = bbox.join(',');
  if (disposition) params.disposition = disposition;
  return apiFetch<any>('/api/v1/leads/geojson', { params });
}

export async function createLeadPin(
  data: LeadPinCreate,
): Promise<LeadPinResponse> {
  return apiFetch<LeadPinResponse>('/api/v1/leads', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateLeadPin(
  pinId: string,
  data: LeadPinUpdate,
): Promise<LeadPinResponse> {
  return apiFetch<LeadPinResponse>(`/api/v1/leads/${pinId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteLeadPin(pinId: string): Promise<void> {
  return apiFetch<void>(`/api/v1/leads/${pinId}`, { method: 'DELETE' });
}

export async function getLeadPinActivities(
  pinId: string,
): Promise<PinActivityListResponse> {
  return apiFetch<PinActivityListResponse>(`/api/v1/leads/${pinId}/activities`);
}

// ===== Helper Types =====

export type { ErrorResponse };
