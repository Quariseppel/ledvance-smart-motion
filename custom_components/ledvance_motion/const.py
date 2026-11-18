"""Constants for the SMART+ motion reader."""

DOMAIN = "ledvance_motion"
CONF_DP = "motion_dp"
CONF_SOURCE = "status_source"
CONF_REGION = "region"
CONF_SID = "sid"
CONF_REFRESH = "refresh_token"
CONF_ONLY_AFTER_SUNSET = "only_after_sunset"
CONF_ACTIVE_MODE = "active_mode"
CONF_ACTIVE_FROM = "active_from"
CONF_ACTIVE_UNTIL = "active_until"
CONF_COVERS = "covers"
CONF_POLL_SECONDS = "poll_seconds"
MODE_ALWAYS = "always"
MODE_SUNSET = "sunset"
MODE_FIXED = "fixed_hours"
MODE_COVERS = "covers_only"
ACTIVE_MODES = (MODE_ALWAYS, MODE_SUNSET, MODE_FIXED, MODE_COVERS)
DEFAULT_FROM = "18:00:00"
DEFAULT_UNTIL = "06:00:00"
POLL_SECONDS = 15
NIGHT_POLL_SECONDS = 5
MIN_POLL_SECONDS = 5
MAX_POLL_SECONDS = 300
CLOUD_BACKOFF_SECONDS = 120
