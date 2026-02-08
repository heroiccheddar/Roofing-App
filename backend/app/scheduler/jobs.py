"""Scheduled background jobs.

Defines all scheduled tasks: data ingestion, scoring runs, alert delivery,
and model calibration. Configured to run via APScheduler.
"""

# TODO: Implement in WP 3.6
# - poll_nws_data() - runs every 6 hours
# - poll_spc_data() - runs daily at 8 AM
# - run_scoring_engine() - runs after data polls complete
# - send_alert_digest() - runs daily at 7 AM
# - calibrate_model() - runs weekly on Sunday
pass
