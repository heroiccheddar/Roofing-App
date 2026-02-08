"""AWS SES email service.

Sends HTML email alerts to roofers with lead zone summaries, mini-maps,
and links to the dashboard. Uses AWS SES send_email() via boto3.

62K emails/month free when sent from AWS compute (App Runner qualifies).
SES configuration set provides open/click tracking.
"""

# TODO: Implement in WP 4.2
# - send_zone_alert_email(roofer, zone) using boto3 SES client
# - HTML email template with Mapbox static map image
# - Score breakdown and CTA link
# - Rate limit: 10 emails/day per roofer
# - Log to alert_log with channel='email'
pass
