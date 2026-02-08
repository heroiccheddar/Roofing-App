"""AWS SNS SMS service.

Sends SMS alerts to roofers about new high-scoring lead zones in their
service areas. Uses AWS SNS publish() to send directly to phone numbers.

SNS handles carrier delivery, retry logic, and opt-out management.
SMS type is set to Transactional for higher delivery priority.
"""

# TODO: Implement in WP 4.1
# - send_zone_alert_sms(roofer, zone) using boto3 SNS client
# - Format message per plan template
# - Check subscription_tier (Pro only)
# - Rate limit: 5 SMS/day per roofer
# - Log to alert_log with channel='sms'
pass
