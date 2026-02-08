/**
 * TypeScript types matching Pydantic API schemas.
 *
 * These types define the API contract for the StormLeads frontend.
 * All datetime fields are strings (ISO 8601 format), UUIDs are strings.
 */

// ===== Common Types =====

export interface ErrorResponse {
  detail: string;
  code?: string;
}

// ===== Authentication =====

export interface AuthRegisterRequest {
  email: string;
  password: string;
  company_name: string;
  phone_number?: string;
  service_area_lat: number;
  service_area_lon: number;
  service_area_radius_km: number;
}

export interface AuthLoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// ===== Account Management =====

export interface ServiceAreaUpdate {
  lat: number;
  lon: number;
  radius_km: number;
}

export interface QuietHours {
  start: string; // HH:MM format
  end: string;   // HH:MM format
}

export interface AlertPreferences {
  min_score: number;
  min_hail_inches: number;
  channels: string[]; // 'email' | 'sms' | 'push'
  quiet_hours?: QuietHours;
}

export interface AccountResponse {
  id: string;
  email: string;
  company_name: string;
  phone_number?: string;
  subscription_tier: string; // 'free' | 'pro'
  alert_preferences: Record<string, any>;
  is_admin: boolean;
  created_at: string;
}

// ===== Lead Zones =====

export interface ZoneListParams {
  min_score?: number;
  hail_min?: number;
  sort_by?: 'score' | 'time' | 'hail';
  page?: number;
  page_size?: number;
}

export interface StormEventBrief {
  id: string;
  source: string; // 'nws' | 'spc' | 'swdi'
  event_type: string; // 'hail' | 'wind' | 'tornado'
  hail_diameter?: number;
  wind_speed?: number;
  event_timestamp: string;
  radar_confidence?: number;
}

export interface ZoneResponse {
  id: string;
  h3_index: string;

  // Scoring components
  composite_score: number;
  damage_prob: number;
  lead_quality: number;
  density_bonus: number;
  predicted_conversion_rate?: number;

  // Score classification
  score_band: string; // 'hot' | 'warm' | 'cool' | 'skip'
  model_version: string;

  // Event aggregation
  event_count: number;
  max_hail_diameter?: number;
  max_wind_speed?: number;
  primary_event_timestamp?: string;

  // Zone lifecycle
  expires_at: string;

  // Geospatial
  centroid_lat: number;
  centroid_lon: number;

  // Timestamps
  created_at: string;
}

export interface ZoneDetailResponse extends ZoneResponse {
  decay_adjusted_score: number;
  hours_since_storm: number;
  events: StormEventBrief[];
}

export interface ZoneListResponse {
  zones: ZoneResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface GeoJSONGeometry {
  type: string;
  coordinates: number[][][]; // [[[lon, lat], ...]]
}

export interface ZoneGeoJSONFeature {
  type: 'Feature';
  geometry: GeoJSONGeometry;
  properties: Record<string, any>;
}

export interface ZoneGeoJSONResponse {
  type: 'FeatureCollection';
  features: ZoneGeoJSONFeature[];
}

// ===== Feedback & Analytics =====

export interface FeedbackCreate {
  // Tier 1: Required
  rating: number; // 1-5

  // Tier 2: Encouraged
  doors_knocked?: number;
  doors_answered?: number;
  visible_damage_count?: number;
  homeowner_interested?: number;

  // Tier 3: Detailed
  inspections_scheduled?: number;
  contracts_signed?: number;
  estimated_revenue?: number;
  roof_type?: string;
  competitor_presence?: 'none' | 'low' | 'medium' | 'high';

  notes?: string;
}

export interface FeedbackUpdate {
  rating?: number;
  doors_knocked?: number;
  doors_answered?: number;
  visible_damage_count?: number;
  homeowner_interested?: number;
  inspections_scheduled?: number;
  contracts_signed?: number;
  estimated_revenue?: number;
  roof_type?: string;
  competitor_presence?: 'none' | 'low' | 'medium' | 'high';
  notes?: string;
}

export interface FeedbackResponse {
  id: string;
  lead_zone_id: string;

  rating: number;
  doors_knocked?: number;
  doors_answered?: number;
  visible_damage_count?: number;
  homeowner_interested?: number;
  inspections_scheduled?: number;
  contracts_signed?: number;
  estimated_revenue?: number;
  roof_type?: string;
  competitor_presence?: string;
  notes?: string;
  zone_score_at_time?: number;

  created_at: string;
  updated_at: string;
}

export interface FeedbackHistoryResponse {
  sessions: FeedbackResponse[];
  total: number;
}

export interface ConversionByBand {
  hot?: number;
  warm?: number;
  cool?: number;
}

export interface ConversionOverTime {
  date: string; // YYYY-MM-DD
  conversion_rate: number;
  zones_canvassed: number;
}

export interface PerformanceAnalytics {
  total_zones_canvassed: number;
  avg_conversion_rate: number;
  best_score_band?: string;
  best_hail_range?: string;
  revenue_per_trip: number;
  conversion_by_band: ConversionByBand;
  conversion_over_time: ConversionOverTime[];
}

// ===== Alerts =====

export interface AlertLogResponse {
  id: string;
  lead_zone_id: string;
  channel: string; // 'sms' | 'email' | 'websocket'
  sent_at: string;
  opened_at?: string;
  acted_on?: string;
  zone_score?: number;
  zone_h3_index?: string;
}

export interface AlertHistoryResponse {
  alerts: AlertLogResponse[];
  total: number;
}

// ===== Internal Admin =====

export interface CalibrationEntry {
  model_version: string;
  region: string;
  hail_size_bucket: string;
  avg_predicted_conversion: number;
  avg_actual_conversion: number;
  prediction_bias: number;
  sample_size: number;
  computed_at: string;
}

export interface CalibrationReport {
  entries: CalibrationEntry[];
  model_version: string;
  total_sample_size: number;
}

export interface WeightChange {
  weight_name: string;
  current_value: number;
  proposed_value: number;
  reason: string;
}

export interface WeightProposal {
  current_weights: Record<string, number>;
  proposed_weights: Record<string, number>;
  changes: WeightChange[];
}

export interface ModelDeployRequest {
  proposed_weights: Record<string, number>;
  notes?: string;
}

export interface ModelDeployResponse {
  model_version: string;
  deployed_at: string;
  weights: Record<string, number>;
}
