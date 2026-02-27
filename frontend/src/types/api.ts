/**
 * TypeScript types matching Pydantic API schemas.
 *
 * These types define the API contract for the RoofIQ frontend.
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
  service_area_lat: number | null;
  service_area_lon: number | null;
}

// ===== Lead Zones =====

export interface ZoneListParams {
  min_score?: number;
  hail_min?: number;
  lead_type?: 'standard' | 'storm_boosted'; // filter: 'all' | 'standard' | 'storm_boosted'
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

export interface FreshnessInfo {
  status: 'fresh' | 'aging' | 'stale';
  age_days: number;
  label: string;
}

export interface ZoneResponse {
  id: string;
  h3_index: string;
  lead_type: string;

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

  // Display
  display_name?: string;

  // Timestamps
  created_at: string;

  // Unified sub-scores
  roof_condition?: number;
  market_quality?: number;
  risk_exposure?: number;
  canvass_efficiency?: number;
  storm_boost?: number;
  base_score?: number;
  has_active_storm?: boolean;

  // Freshness
  freshness?: FreshnessInfo;
}

export interface ScoreFactor {
  name: string;
  label: string;
  percentile: number;
  weight: number;
  contribution: number;
}

export interface ZoneDetailResponse extends ZoneResponse {
  decay_adjusted_score: number;
  hours_since_storm: number;
  events: StormEventBrief[];
  avg_roof_age_years?: number;
  avg_median_income?: number;
  avg_vacancy_rate?: number;
  avg_single_family_pct?: number;
  avg_pct_built_before_1980?: number;
  nri_hail_risk?: string;
  nri_wind_risk?: string;
  nri_tornado_risk?: string;
  total_building_count?: number;
  avg_building_area_sqm?: number;
  hail_exposure_score?: number;
  hail_events_3yr?: number;
  fema_disaster_count?: number;
  fema_disaster_score?: number;
  tree_canopy_mean_pct?: number;
  tree_canopy_risk_score?: number;
  dominant_decade?: string;
  age_clustering_score?: number;
  pct_cost_burdened?: number;
  hpi_5yr_change?: number;
  verified_damage_5yr_usd?: number;
  climate_weathering_score?: number;
  svi_overall?: number;
  svi_housing_type?: number;
  ruca_category?: string;
  bps_single_family_permits?: number;
  bps_all_permits?: number;
  bps_total_value?: number;
  ej_lead_paint?: number;
  ej_percentile?: number;
  flood_risk_category?: string;
  flood_insurance_required?: boolean;
  redfin_median_sale_price?: number;
  redfin_median_dom?: number;
  redfin_price_drop_pct?: number;
  score_factors?: ScoreFactor[];
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

export interface TractGeoJSONResponse {
  type: 'FeatureCollection';
  features: ZoneGeoJSONFeature[];
}

// ===== Recommendations =====

export interface RecommendedZone {
  zone_id: string;
  h3_index: string;
  display_name?: string;
  composite_score: number;
  recommendation_score: number;
  distance_km: number;
  last_canvassed_at?: string;
  has_active_storm: boolean;
  storm_boost?: number;
  centroid_lat: number;
  centroid_lon: number;
  score_band: string;
  reason: string;
}

export interface RecommendationResponse {
  zones: RecommendedZone[];
  generated_at: string;
}

// ===== Route Planning =====

export interface RouteRequest {
  zone_ids: string[];
  start_lat: number;
  start_lon: number;
}

export interface RouteWaypoint {
  zone_id: string;
  display_name?: string;
  lat: number;
  lon: number;
  order: number;
}

export interface RouteResponse {
  waypoints: RouteWaypoint[];
  geometry: { type: string; coordinates: number[][] };
  total_distance_km: number;
  total_duration_minutes: number;
  generated_at: string;
}

// ===== Zone Feedback (POC) =====

export interface ZoneFeedbackCreate {
  rating: number; // 1-5 stars
  visible_damage?: boolean;
  notes?: string;
}

export interface ZoneFeedbackResponse {
  id: string;
  lead_zone_id: string;
  roofer_account_id: string;
  rating: number;
  visible_damage?: boolean;
  notes?: string;
  zone_score_at_feedback?: number;
  created_at: string;
}

export interface ZoneFeedbackListResponse {
  feedbacks: ZoneFeedbackResponse[];
  total: number;
}

// ===== Canvass Sessions =====

export interface CanvassSessionCreate {
  notes?: string;
}

export interface CanvassSessionUpdate {
  doors_knocked?: number;
  doors_answered?: number;
  visible_damage_count?: number;
  homeowner_interested?: number;
  inspections_scheduled?: number;
  contracts_signed?: number;
  estimated_revenue?: number;
  roof_type?: string;
  competitor_presence?: string;
  rating?: number;
  notes?: string;
}

export interface CanvassSessionResponse {
  id: string;
  lead_zone_id: string;
  roofer_account_id: string;
  rating?: number | null;
  doors_knocked?: number | null;
  doors_answered?: number | null;
  visible_damage_count?: number | null;
  homeowner_interested?: number | null;
  inspections_scheduled?: number | null;
  contracts_signed?: number | null;
  estimated_revenue?: number | null;
  roof_type?: string | null;
  competitor_presence?: string | null;
  notes?: string | null;
  zone_score_at_time?: number | null;
  created_at: string;
  updated_at: string;
}

export interface CanvassSessionListResponse {
  sessions: CanvassSessionResponse[];
  total: number;
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

// ===== Properties (Parcel Data) =====

export interface PropertyResponse {
  id: string;
  parcel_id: string;
  address?: string;
  owner_name?: string;
  year_built?: number;
  estimated_roof_age?: number;
  assessed_value?: number;
  land_value?: number;
  improvement_value?: number;
  square_footage?: number;
  lot_size_acres?: number;
  property_type?: string;
  zoning?: string;
  bedrooms?: number;
  bathrooms?: number;
  stories?: number;
  last_sale_date?: string;
  last_sale_price?: number;
  latitude?: number;
  longitude?: number;
}

export interface PropertyListResponse {
  properties: PropertyResponse[];
  total: number;
  tract_geoid: string;
  source_county?: string;
  data_freshness?: string;
  has_county_adapter: boolean;
}

// ===== Lead Pins =====

export type LeadPinDisposition =
  | 'not_home'
  | 'callback'
  | 'interested'
  | 'inspection_set'
  | 'contract_signed'
  | 'not_interested';

export interface LeadPinCreate {
  lat: number;
  lon: number;
  address?: string;
  disposition: LeadPinDisposition;
  notes?: string;
  property_id?: string;
  lead_zone_id?: string;
  callback_date?: string;
}

export interface LeadPinUpdate {
  disposition?: LeadPinDisposition;
  notes?: string;
  callback_date?: string;
}

export interface LeadPinResponse {
  id: string;
  roofer_account_id: string;
  property_id?: string;
  lead_zone_id?: string;
  lat: number;
  lon: number;
  address?: string;
  disposition: LeadPinDisposition;
  notes?: string;
  callback_date?: string;
  roofer_name?: string;
  created_at: string;
  updated_at: string;
}

export interface LeadPinListResponse {
  pins: LeadPinResponse[];
  total: number;
}

export interface PinActivityCreate {
  notes: string;
}

export interface PinActivityResponse {
  id: string;
  lead_pin_id: string;
  disposition: LeadPinDisposition;
  notes?: string;
  created_at: string;
}

export interface PinActivityListResponse {
  activities: PinActivityResponse[];
  total: number;
}

// ===== Organization =====

export interface OrgCreate {
  name: string;
}

export interface OrgJoin {
  invite_code: string;
}

export interface OrgMember {
  id: string;
  email: string;
  company_name: string;
  org_role: 'owner' | 'member';
}

export interface OrgResponse {
  id: string;
  name: string;
  invite_code: string;
  created_by: string;
  created_at: string;
}

export interface OrgDetailResponse extends OrgResponse {
  members: OrgMember[];
}

// ===== Property GeoJSON (Map Layer) =====

export interface PropertyGeoJSONProperties {
  id: string;
  address: string | null;
  disposition: LeadPinDisposition | null;
  estimated_roof_age: number | null;
  year_built: number | null;
}

export interface PropertyGeoJSONFeature {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: PropertyGeoJSONProperties;
}

export interface PropertyGeoJSONResponse {
  type: 'FeatureCollection';
  features: PropertyGeoJSONFeature[];
}

// ===== Leaderboard & Metrics =====

export type LeaderboardPeriod = 'this_week' | 'this_month' | 'all_time'

export interface LeaderboardMember {
  roofer_account_id: string
  company_name: string
  email: string
  total_pins: number
  not_home: number
  callback: number
  interested: number
  inspection_set: number
  contract_signed: number
  not_interested: number
  conversion_rate: number
}

export interface LeaderboardResponse {
  current_user_id: string
  period: LeaderboardPeriod
  period_start: string | null
  members: LeaderboardMember[]
}
