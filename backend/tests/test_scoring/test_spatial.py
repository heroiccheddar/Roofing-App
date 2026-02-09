"""Unit tests for spatial.py module.

Tests spatial helper functions with mocked database calls.
Does not require a live database connection.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from shapely.geometry import Point, Polygon
from geoalchemy2.shape import from_shape

from app.scoring.spatial import (
    point_to_h3,
    h3_to_boundary,
    compute_housing_density,
    compute_weighted_demographics,
    cluster_events_to_h3,
    build_zone_boundary,
    get_intersecting_tracts,
)


class TestPointToH3:
    """Tests for point_to_h3() function."""

    def test_point_to_h3_returns_string(self):
        """Test that point_to_h3 returns a valid H3 index string."""
        lat, lon = 39.7392, -104.9903  # Denver, CO

        h3_index = point_to_h3(lat, lon)

        assert isinstance(h3_index, str)
        assert len(h3_index) > 0

    def test_point_to_h3_resolution_7(self):
        """Test that default resolution is 7."""
        lat, lon = 39.7392, -104.9903

        h3_index_default = point_to_h3(lat, lon)
        h3_index_explicit = point_to_h3(lat, lon, resolution=7)

        assert h3_index_default == h3_index_explicit

    @pytest.mark.parametrize("resolution", [4, 5, 6, 7, 8, 9])
    def test_point_to_h3_different_resolutions(self, resolution):
        """Test that point_to_h3 works with different resolution levels."""
        lat, lon = 39.7392, -104.9903

        h3_index = point_to_h3(lat, lon, resolution=resolution)

        assert isinstance(h3_index, str)
        assert len(h3_index) > 0

    def test_point_to_h3_different_locations_different_indices(self):
        """Test that different locations produce different H3 indices."""
        denver = point_to_h3(39.7392, -104.9903)
        chicago = point_to_h3(41.8781, -87.6298)
        new_york = point_to_h3(40.7128, -74.0060)

        assert denver != chicago
        assert chicago != new_york
        assert denver != new_york

    def test_point_to_h3_same_location_same_index(self):
        """Test that same location consistently produces same H3 index."""
        lat, lon = 39.7392, -104.9903

        h3_index_1 = point_to_h3(lat, lon)
        h3_index_2 = point_to_h3(lat, lon)

        assert h3_index_1 == h3_index_2


class TestH3ToBoundary:
    """Tests for h3_to_boundary() function."""

    def test_h3_to_boundary_returns_closed_ring(self):
        """Test that boundary is a closed ring (first coord == last coord)."""
        lat, lon = 39.7392, -104.9903
        h3_index = point_to_h3(lat, lon)

        coords = h3_to_boundary(h3_index)

        assert coords[0] == coords[-1]

    def test_h3_to_boundary_returns_lon_lat_order(self):
        """Test that coordinates are in (lon, lat) order, not (lat, lon)."""
        lat, lon = 39.7392, -104.9903
        h3_index = point_to_h3(lat, lon)

        coords = h3_to_boundary(h3_index)

        # Each coord should be (lon, lat)
        for coord in coords:
            assert len(coord) == 2
            lon_val, lat_val = coord
            # Longitude should be roughly -180 to 180
            # Latitude should be roughly -90 to 90
            assert -180 <= lon_val <= 180
            assert -90 <= lat_val <= 90

    def test_h3_to_boundary_creates_valid_polygon(self):
        """Test that boundary coordinates can create a valid Shapely polygon."""
        lat, lon = 39.7392, -104.9903
        h3_index = point_to_h3(lat, lon)

        coords = h3_to_boundary(h3_index)
        polygon = Polygon(coords)

        assert polygon.is_valid
        assert polygon.area > 0

    def test_h3_to_boundary_has_hexagon_shape(self):
        """Test that boundary has approximately 7 points (6 vertices + 1 closure)."""
        lat, lon = 39.7392, -104.9903
        h3_index = point_to_h3(lat, lon)

        coords = h3_to_boundary(h3_index)

        # H3 hexagons have 6 vertices, plus 1 closure point = 7 total
        assert len(coords) == 7


class TestComputeHousingDensity:
    """Tests for compute_housing_density() function."""

    def test_compute_housing_density_normal(self):
        """Test housing density calculation with normal values."""
        tract = MagicMock()
        tract.housing_units = 1000
        tract.area_sq_km = 10.0

        density = compute_housing_density(tract)

        assert density == 100.0  # 1000 / 10

    def test_compute_housing_density_zero_area(self):
        """Test that zero area returns 0.0 to avoid division by zero."""
        tract = MagicMock()
        tract.housing_units = 1000
        tract.area_sq_km = 0.0

        density = compute_housing_density(tract)

        assert density == 0.0

    def test_compute_housing_density_none_housing_units(self):
        """Test that None housing_units returns 0.0."""
        tract = MagicMock()
        tract.housing_units = None
        tract.area_sq_km = 10.0

        density = compute_housing_density(tract)

        assert density == 0.0

    def test_compute_housing_density_none_area(self):
        """Test that None area returns 0.0."""
        tract = MagicMock()
        tract.housing_units = 1000
        tract.area_sq_km = None

        density = compute_housing_density(tract)

        assert density == 0.0

    def test_compute_housing_density_both_none(self):
        """Test that both None values return 0.0."""
        tract = MagicMock()
        tract.housing_units = None
        tract.area_sq_km = None

        density = compute_housing_density(tract)

        assert density == 0.0

    def test_compute_housing_density_zero_housing_units(self):
        """Test that zero housing units returns 0.0."""
        tract = MagicMock()
        tract.housing_units = 0
        tract.area_sq_km = 10.0

        density = compute_housing_density(tract)

        assert density == 0.0


class TestComputeWeightedDemographics:
    """Tests for compute_weighted_demographics() function."""

    def test_compute_weighted_demographics_empty(self):
        """Test that empty tract list returns zeros."""
        demographics = compute_weighted_demographics([])

        assert demographics["avg_owner_occupied_pct"] == 0.0
        assert demographics["avg_median_home_value"] == 0.0
        assert demographics["avg_median_year_built"] == 0.0
        assert demographics["total_housing_units"] == 0
        assert demographics["total_population"] == 0
        assert demographics["avg_housing_density"] == 0.0

    def test_compute_weighted_demographics_single_tract(self):
        """Test weighted demographics with a single tract."""
        tract = MagicMock()
        tract.area_sq_km = 10.0
        tract.owner_occupied_pct = 65.0
        tract.median_home_value = 250000
        tract.median_year_built = 1985
        tract.housing_units = 1000
        tract.population = 2500

        demographics = compute_weighted_demographics([tract])

        # With single tract, weighted average == actual value
        assert demographics["avg_owner_occupied_pct"] == 65.0
        assert demographics["avg_median_home_value"] == 250000
        assert demographics["avg_median_year_built"] == 1985
        assert demographics["total_housing_units"] == 1000
        assert demographics["total_population"] == 2500
        assert demographics["avg_housing_density"] == 100.0  # 1000 / 10

    def test_compute_weighted_demographics_multiple_tracts_equal_area(self):
        """Test weighted demographics with equal-area tracts."""
        tract1 = MagicMock()
        tract1.area_sq_km = 10.0
        tract1.owner_occupied_pct = 60.0
        tract1.median_home_value = 200000
        tract1.median_year_built = 1980
        tract1.housing_units = 1000
        tract1.population = 2000

        tract2 = MagicMock()
        tract2.area_sq_km = 10.0
        tract2.owner_occupied_pct = 80.0
        tract2.median_home_value = 300000
        tract2.median_year_built = 1990
        tract2.housing_units = 1500
        tract2.population = 3000

        demographics = compute_weighted_demographics([tract1, tract2])

        # Equal areas -> simple average
        assert demographics["avg_owner_occupied_pct"] == 70.0
        assert demographics["avg_median_home_value"] == 250000
        assert demographics["avg_median_year_built"] == 1985
        assert demographics["total_housing_units"] == 2500
        assert demographics["total_population"] == 5000

    def test_compute_weighted_demographics_multiple_tracts_different_area(self):
        """Test weighted demographics with different-area tracts."""
        # Tract 1: 75% of total area
        tract1 = MagicMock()
        tract1.area_sq_km = 30.0
        tract1.owner_occupied_pct = 60.0
        tract1.median_home_value = 200000
        tract1.median_year_built = 1980
        tract1.housing_units = 3000
        tract1.population = 6000

        # Tract 2: 25% of total area
        tract2 = MagicMock()
        tract2.area_sq_km = 10.0
        tract2.owner_occupied_pct = 80.0
        tract2.median_home_value = 400000
        tract2.median_year_built = 2000
        tract2.housing_units = 1000
        tract2.population = 2000

        demographics = compute_weighted_demographics([tract1, tract2])

        # Weighted average: tract1 gets 0.75 weight, tract2 gets 0.25 weight
        expected_owner = 60.0 * 0.75 + 80.0 * 0.25  # 65.0
        expected_value = 200000 * 0.75 + 400000 * 0.25  # 250000
        expected_year = 1980 * 0.75 + 2000 * 0.25  # 1985

        assert demographics["avg_owner_occupied_pct"] == expected_owner
        assert demographics["avg_median_home_value"] == expected_value
        assert demographics["avg_median_year_built"] == expected_year
        assert demographics["total_housing_units"] == 4000
        assert demographics["total_population"] == 8000

    def test_compute_weighted_demographics_skips_none_values(self):
        """Test that tracts with None values are handled gracefully."""
        tract1 = MagicMock()
        tract1.area_sq_km = 10.0
        tract1.owner_occupied_pct = 60.0
        tract1.median_home_value = None  # Missing value
        tract1.median_year_built = 1980
        tract1.housing_units = 1000
        tract1.population = 2000

        tract2 = MagicMock()
        tract2.area_sq_km = 10.0
        tract2.owner_occupied_pct = 80.0
        tract2.median_home_value = 300000
        tract2.median_year_built = None  # Missing value
        tract2.housing_units = 1500
        tract2.population = 3000

        demographics = compute_weighted_demographics([tract1, tract2])

        # Should still compute averages, skipping None values
        assert demographics["avg_owner_occupied_pct"] == 70.0
        # Only tract2 contributes to home value
        assert demographics["avg_median_home_value"] == 150000  # 300000 * 0.5
        # Only tract1 contributes to year built
        assert demographics["avg_median_year_built"] == 990  # 1980 * 0.5

    def test_compute_weighted_demographics_zero_total_area(self):
        """Test that zero total area returns zeros (except totals)."""
        tract = MagicMock()
        tract.area_sq_km = 0.0
        tract.owner_occupied_pct = 65.0
        tract.median_home_value = 250000
        tract.median_year_built = 1985
        tract.housing_units = 1000
        tract.population = 2500

        demographics = compute_weighted_demographics([tract])

        assert demographics["avg_owner_occupied_pct"] == 0.0
        assert demographics["avg_median_home_value"] == 0.0
        assert demographics["avg_median_year_built"] == 0.0
        assert demographics["total_housing_units"] == 1000
        assert demographics["total_population"] == 2500
        assert demographics["avg_housing_density"] == 0.0


class TestClusterEventsToH3:
    """Tests for cluster_events_to_h3() function."""

    def test_cluster_events_to_h3_groups_correctly(self):
        """Test that events in the same area are grouped together."""
        # Create mock events with Point geometries at same location
        lat, lon = 39.7392, -104.9903
        point = Point(lon, lat)  # Note: Point takes (x, y) = (lon, lat)

        event1 = MagicMock()
        event1.id = 1
        event1.location = from_shape(point, srid=4326)

        event2 = MagicMock()
        event2.id = 2
        event2.location = from_shape(point, srid=4326)

        # Create event at different location
        point2 = Point(-95.0, 35.0)
        event3 = MagicMock()
        event3.id = 3
        event3.location = from_shape(point2, srid=4326)

        clusters = cluster_events_to_h3([event1, event2, event3])

        # Should have 2 clusters
        assert len(clusters) == 2

        # Find cluster with events 1 and 2
        h3_index_1 = point_to_h3(lat, lon)
        assert h3_index_1 in clusters
        assert len(clusters[h3_index_1]) == 2
        assert event1 in clusters[h3_index_1]
        assert event2 in clusters[h3_index_1]

        # Find cluster with event 3
        h3_index_2 = point_to_h3(35.0, -95.0)
        assert h3_index_2 in clusters
        assert len(clusters[h3_index_2]) == 1
        assert event3 in clusters[h3_index_2]

    def test_cluster_events_to_h3_skips_none_locations(self):
        """Test that events with None locations are skipped."""
        point = Point(-104.9903, 39.7392)

        event1 = MagicMock()
        event1.location = from_shape(point, srid=4326)

        event2 = MagicMock()
        event2.location = None  # No location

        clusters = cluster_events_to_h3([event1, event2])

        # Only event1 should be clustered
        assert len(clusters) >= 1
        total_events = sum(len(events) for events in clusters.values())
        assert total_events == 1

    def test_cluster_events_to_h3_empty_list(self):
        """Test that empty event list returns empty dict."""
        clusters = cluster_events_to_h3([])

        assert clusters == {}

    def test_cluster_events_to_h3_different_resolutions(self):
        """Test that different resolutions produce different clustering."""
        point = Point(-104.9903, 39.7392)
        event = MagicMock()
        event.location = from_shape(point, srid=4326)

        clusters_res6 = cluster_events_to_h3([event], resolution=6)
        clusters_res7 = cluster_events_to_h3([event], resolution=7)
        clusters_res8 = cluster_events_to_h3([event], resolution=8)

        # Different resolutions should produce different H3 indices
        h3_indices = [
            list(clusters_res6.keys())[0],
            list(clusters_res7.keys())[0],
            list(clusters_res8.keys())[0],
        ]

        # All should be different
        assert len(set(h3_indices)) == 3


class TestBuildZoneBoundary:
    """Tests for build_zone_boundary() function."""

    def test_build_zone_boundary_returns_wkt(self):
        """Test that build_zone_boundary returns valid WKT strings."""
        lat, lon = 39.7392, -104.9903
        h3_index = point_to_h3(lat, lon)

        boundary_wkt, centroid_wkt = build_zone_boundary(h3_index)

        # Check that both are strings
        assert isinstance(boundary_wkt, str)
        assert isinstance(centroid_wkt, str)

        # Check WKT format
        assert boundary_wkt.startswith("POLYGON")
        assert centroid_wkt.startswith("POINT")

    def test_build_zone_boundary_creates_valid_geometries(self):
        """Test that WKT strings can be parsed back to valid geometries."""
        from shapely import wkt

        lat, lon = 39.7392, -104.9903
        h3_index = point_to_h3(lat, lon)

        boundary_wkt, centroid_wkt = build_zone_boundary(h3_index)

        # Parse WKT back to geometries
        boundary_geom = wkt.loads(boundary_wkt)
        centroid_geom = wkt.loads(centroid_wkt)

        # Validate
        assert boundary_geom.is_valid
        assert centroid_geom.is_valid
        assert isinstance(boundary_geom, Polygon)
        assert isinstance(centroid_geom, Point)

    def test_build_zone_boundary_centroid_inside_boundary(self):
        """Test that centroid is inside the boundary polygon."""
        from shapely import wkt

        lat, lon = 39.7392, -104.9903
        h3_index = point_to_h3(lat, lon)

        boundary_wkt, centroid_wkt = build_zone_boundary(h3_index)

        boundary_geom = wkt.loads(boundary_wkt)
        centroid_geom = wkt.loads(centroid_wkt)

        # Centroid should be inside or on boundary
        assert boundary_geom.contains(centroid_geom) or boundary_geom.touches(centroid_geom)


class TestGetIntersectingTracts:
    """Tests for get_intersecting_tracts() async function."""

    @pytest.mark.asyncio
    async def test_get_intersecting_tracts_returns_list(self):
        """Test that get_intersecting_tracts returns a list of tracts."""
        session = AsyncMock()

        # Mock the query result
        mock_tract = MagicMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_tract]
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        geometry_wkt = "POLYGON((-105 40, -104 40, -104 39, -105 39, -105 40))"

        tracts = await get_intersecting_tracts(session, geometry_wkt)

        assert isinstance(tracts, list)
        assert len(tracts) == 1
        assert tracts[0] == mock_tract

    @pytest.mark.asyncio
    async def test_get_intersecting_tracts_empty_result(self):
        """Test that get_intersecting_tracts handles empty results."""
        session = AsyncMock()

        # Mock empty query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        geometry_wkt = "POLYGON((-105 40, -104 40, -104 39, -105 39, -105 40))"

        tracts = await get_intersecting_tracts(session, geometry_wkt)

        assert tracts == []
