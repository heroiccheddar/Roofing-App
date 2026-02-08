"""Storm Prediction Center report scraper.

Scrapes preliminary storm reports from SPC's website for more recent
data than the NWS database provides (often 1-3 day lag vs 30+ days).

SPC Reports: https://www.spc.noaa.gov/climo/reports/
"""

# TODO: Implement in WP 1.1
# - async fetch_daily_reports(date: datetime.date) -> list[dict]
# - parse SPC CSV format
# - convert to StormEvent model instances
# - handle different report types (hail, wind, tornado)
# - deduplicate with NWS data
pass
