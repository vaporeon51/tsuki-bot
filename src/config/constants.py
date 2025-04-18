UPVOTE_EMOTE = "❤️"
REPORT_EMOTE = "⚠️"
TSUKI_NOM = "🍱"
TSUKI_HARAM_HUG = "💕"

# Number of seconds to wait before updating db based on reactions
REACT_WAIT_SEC = 3 * 60

# Number of reports to eliminate a role + link combination from being shown
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
