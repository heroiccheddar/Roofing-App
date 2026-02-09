"""Unit tests for SWDI MESH data fetcher."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.ingestion.swdi_fetcher import (
    fetch_swdi_mesh,
    fetch_swdi_for_warning,
    _parse_swdi_response,
    _parse_swdi_timestamp,
)


class TestParseSWDITimestamp:
    """Test SWDI timestamp parsing."""

    def test_parse_standard_format(self):
        """Test parsing YYYYMMDD_HHMM format."""
        result = _parse_swdi_timestamp("20250515_2030")
        assert result == datetime(2025, 5, 15, 20, 30)

    def test_parse_compact_format(self):
        """Test parsing YYYYMMDDHHMM format."""
        result = _parse_swdi_timestamp("202505152030")
        assert result == datetime(2025, 5, 15, 20, 30)

    def test_parse_iso_format(self):
        """Test parsing ISO format as fallback."""
        result = _parse_swdi_timestamp("2025-05-15T20:30:00Z")
        assert result.year == 2025
        assert result.month == 5
        assert result.day == 15

    def test_parse_invalid_format(self):
        """Test that invalid formats raise ValueError."""
        with pytest.raises(ValueError):
            _parse_swdi_timestamp("invalid")


class TestParseSWDIResponse:
    """Test SWDI API response parsing."""

    def test_parse_result_data_structure(self):
        """Test parsing response with result.data structure."""
        response = {
            "result": {
                "data": [
                    {"WSR_ID": "KTLX", "CELL_ID": "A3"},
                    {"WSR_ID": "KOKC", "CELL_ID": "B1"},
                ],
                "totalCount": 2,
            }
        }
        records = _parse_swdi_response(response)
        assert len(records) == 2
        assert records[0]["WSR_ID"] == "KTLX"
        assert records[1]["WSR_ID"] == "KOKC"

    def test_parse_direct_array(self):
        """Test parsing response as direct array."""
        response = [
            {"WSR_ID": "KTLX", "CELL_ID": "A3"},
            {"WSR_ID": "KOKC", "CELL_ID": "B1"},
        ]
        records = _parse_swdi_response(response)
        assert len(records) == 2

    def test_parse_data_key(self):
        """Test parsing response with top-level data key."""
        response = {
            "data": [
                {"WSR_ID": "KTLX", "CELL_ID": "A3"},
            ]
        }
        records = _parse_swdi_response(response)
        assert len(records) == 1

    def test_parse_empty_response(self):
        """Test parsing empty response."""
        assert _parse_swdi_response({}) == []
        assert _parse_swdi_response([]) == []
        assert _parse_swdi_response({"result": {}}) == []


@pytest.mark.asyncio
class TestFetchSWDIMesh:
    """Test SWDI MESH data fetching."""

    @patch("app.ingestion.swdi_fetcher.httpx.AsyncClient")
    async def test_fetch_success(self, mock_client_class):
        """Test successful MESH data fetch."""
        # Mock SWDI API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "data": [
                    {
                        "WSR_ID": "KTLX",
                        "CELL_ID": "A3",
                        "ZTIME": "20250515_2030",
                        "LON": "-97.48",
                        "LAT": "35.22",
                        "MAX_SIZE": "2.50",
                        "POSH": "80",
                    }
                ]
            }
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = AsyncMock()
        mock_client_class.return_value = mock_client

        # Mock database session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
        mock_session.commit = AsyncMock()

        # Test fetch
        bbox = (-98.0, 35.0, -97.0, 36.0)
        start = datetime(2025, 5, 15, 0, 0)
        end = datetime(2025, 5, 16, 0, 0)

        result = await fetch_swdi_mesh(mock_session, bbox, start, end)

        assert result["fetched"] == 1
        assert result["new"] == 1
        assert result["existing"] == 0
        assert result["errors"] == 0

    @patch("app.ingestion.swdi_fetcher.httpx.AsyncClient")
    async def test_fetch_timeout_retry(self, mock_client_class):
        """Test that timeouts trigger retries."""
        import httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = AsyncMock()
        mock_client_class.return_value = mock_client

        mock_session = AsyncMock()

        bbox = (-98.0, 35.0, -97.0, 36.0)
        start = datetime(2025, 5, 15, 0, 0)
        end = datetime(2025, 5, 16, 0, 0)

        # Should return empty results after retries
        result = await fetch_swdi_mesh(mock_session, bbox, start, end)

        assert result["fetched"] == 0
        assert result["errors"] == 1

    @patch("app.ingestion.swdi_fetcher.httpx.AsyncClient")
    async def test_fetch_empty_results(self, mock_client_class):
        """Test handling of empty SWDI results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": {"data": [], "totalCount": 0}}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = AsyncMock()
        mock_client_class.return_value = mock_client

        mock_session = AsyncMock()

        bbox = (-98.0, 35.0, -97.0, 36.0)
        start = datetime(2025, 5, 15, 0, 0)
        end = datetime(2025, 5, 16, 0, 0)

        result = await fetch_swdi_mesh(mock_session, bbox, start, end)

        assert result["fetched"] == 0
        assert result["new"] == 0
        assert result["errors"] == 0


@pytest.mark.asyncio
class TestFetchSWDIForWarning:
    """Test SWDI fetching for warning polygons."""

    @patch("app.ingestion.swdi_fetcher.fetch_swdi_mesh")
    async def test_fetch_for_warning_computes_bbox(self, mock_fetch_mesh):
        """Test that warning polygon is converted to bbox correctly."""
        mock_fetch_mesh.return_value = {"fetched": 5, "new": 3, "existing": 2, "errors": 0}

        mock_session = AsyncMock()

        # Simple square polygon
        warning_wkt = "POLYGON((-97.6 35.4, -97.4 35.4, -97.4 35.6, -97.6 35.6, -97.6 35.4))"
        warning_time = datetime(2025, 5, 15, 20, 30)

        result = await fetch_swdi_for_warning(
            mock_session,
            warning_wkt,
            warning_time,
            time_window_hours=2,
        )

        # Verify fetch_swdi_mesh was called
        assert mock_fetch_mesh.called
        call_args = mock_fetch_mesh.call_args

        # Check that bbox was computed (with buffer)
        bbox = call_args[0][1]
        assert len(bbox) == 4
        assert bbox[0] < -97.6  # west with buffer
        assert bbox[1] < 35.4   # south with buffer
        assert bbox[2] > -97.4  # east with buffer
        assert bbox[3] > 35.6   # north with buffer

        # Check time window
        start_date = call_args[0][2]
        end_date = call_args[0][3]
        assert start_date == warning_time - timedelta(hours=2)
        assert end_date == warning_time + timedelta(hours=2)

        assert result == mock_fetch_mesh.return_value

    @patch("app.ingestion.swdi_fetcher.fetch_swdi_mesh")
    async def test_fetch_for_warning_invalid_wkt(self, mock_fetch_mesh):
        """Test handling of invalid WKT."""
        mock_session = AsyncMock()

        result = await fetch_swdi_for_warning(
            mock_session,
            "INVALID WKT",
            datetime.utcnow(),
        )

        # Should return error result without calling fetch
        assert result["errors"] == 1
        assert not mock_fetch_mesh.called


@pytest.mark.asyncio
class TestSWDIIntegration:
    """Integration tests for SWDI workflow."""

    @patch("app.ingestion.swdi_fetcher.httpx.AsyncClient")
    async def test_end_to_end_warning_workflow(self, mock_client_class):
        """Test complete workflow: warning arrives -> MESH fetched -> records created."""
        # Mock SWDI API with realistic MESH data
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "data": [
                    {
                        "WSR_ID": "KTLX",
                        "CELL_ID": "A3",
                        "ZTIME": "20250515_2030",
                        "LON": "-97.48",
                        "LAT": "35.22",
                        "MAX_SIZE": "2.50",
                        "POSH": "80",
                    },
                    {
                        "WSR_ID": "KTLX",
                        "CELL_ID": "B1",
                        "ZTIME": "20250515_2035",
                        "LON": "-97.45",
                        "LAT": "35.25",
                        "MAX_SIZE": "1.75",
                        "POSH": "60",
                    },
                ]
            }
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = AsyncMock()
        mock_client_class.return_value = mock_client

        # Mock database
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
        mock_session.commit = AsyncMock()

        # Simulate NWS warning
        warning_polygon = "POLYGON((-97.6 35.1, -97.3 35.1, -97.3 35.4, -97.6 35.4, -97.6 35.1))"
        warning_time = datetime(2025, 5, 15, 20, 28)

        # Fetch MESH data for warning
        result = await fetch_swdi_for_warning(
            mock_session,
            warning_polygon,
            warning_time,
            time_window_hours=1,
        )

        # Should have fetched and created 2 records
        assert result["fetched"] == 2
        assert result["new"] == 2
        assert result["errors"] == 0

        # Verify database session was committed
        mock_session.commit.assert_called_once()
