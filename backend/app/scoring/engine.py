"""Main scoring engine for lead zones.

Orchestrates the scoring pipeline: spatial aggregation, weight application,
demographic enrichment, and temporal decay. Produces scored LeadZone records.
"""

# TODO: Implement in WP 2.1
# - async score_h3_hexagons(storm_events: list[StormEvent], resolution: int = 8)
# - aggregate storm events to H3 cells
# - apply weights from ModelCalibration
# - enrich with census data
# - calculate composite score (0-100)
# - return list of LeadZone instances
pass
