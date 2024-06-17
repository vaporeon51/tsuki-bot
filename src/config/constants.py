UPVOTE_EMOTE = "🔼"
DOWNVOTE_EMOTE = "🔽"
REPORT_EMOTE = "⚠️"

# Number of seconds to wait before updating db based on reactions
REACT_WAIT_SEC = 3 * 60

# Number of reports to eliminate a role + link combination from being shown
REPORT_THRESHOLD = 5

# 10x net upvotes translates to 2x the probability so log(2)/log(10) = 0.30
SAMPLING_EXPONENT = 0.30102999566
