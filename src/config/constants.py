TSUKI_NOM = "🐰"
TSUKI_HARAM_HUG = "💕"

# Number of user reports to hide a role + link combination.
REPORT_THRESHOLD = 5

# 20x net upvotes translates to 2x the probability so log(2)/log(20)
SAMPLING_EXPONENT = 0.23137821316

# Cap on the contribution of initial reactions from kpf to weight
INITIAL_REACT_CAP = 100

# Size of most recently sent URLs queue to prevent duplicates
RECENTLY_SENT_QUEUE_SIZE = 10

# Size of cache for guild settings
GUILD_SETTINGS_CACHE_SIZE = 100

# Window seconds for scanning new posts
REDDIT_FEED_WINDOW = 5 * 60

# Max attachments for reddit feed
REDDIT_MAX_ATTACHMENTS = 10
REDDIT_MAX_ATTACHMENT_BYTES = 100 * 1024 * 1024

# Content recovery scheduler and conservative Imgur upload budget.
CONTENT_RECOVERY_CLI_ROLE_ID = "1000863360776147054"
CONTENT_RECOVERY_BATCH_SIZE = 70
CONTENT_RECOVERY_INTERVAL_SECONDS = 75 * 60
CONTENT_RECOVERY_UPLOAD_INTERVAL = 2.0
CONTENT_RECOVERY_MAX_UPLOADS_PER_HOUR = 100
# A replacement removes 1, 3, then 5 leading frames at generations 1–3.
# Generation 3 is the final permitted recovery attempt.
CONTENT_RECOVERY_MAX_GENERATION = 3
CONTENT_RECOVERY_MAX_ATTEMPTS = 3

# Background dead-link checker.  Probe messages are posted to this private test
# channel and deleted after Discord has had a moment to unfurl the URL.
DEAD_LINK_CHECK_CHANNEL_ID = 1537540189595901952
DEAD_LINK_CHECK_INTERVAL_SECONDS = 7
DEAD_LINK_CHECK_BATCH_SIZE = 100
