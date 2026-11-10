
from budget import estimate_tokens

COMPACT_KEEP_FRACTION = 0.30

# --- Compression Layer ---

# The compression layer compresses the context of the session,
# making the length below the threshold.

def compact_keep_budget(window, trigger):
	budget = int(window * COMPACT_KEEP_FRACTION)
	if trigger > 0 and budget > trigger // 2:
		budget = trigger // 2
	return budget

def safe_split_index(history, keep_budget):
	user_turns = [i for i, m in enumerate(history) if m.get("role") == "user"]
	if len(user_turns) <= 1:
		return 0  # at least two user msgs
	kept_from = user_turns[-1]
	for k in range(len(user_turns) - 2, -1, -1):
		if estimate_tokens(history[user_turns[k]:]) > keep_budget:
			break
		kept_from = user_turns[k]
	return kept_from

COMPRESSION_PROMPT = """The conversation ends here. You are no longer continuing the dialogue but switching to "summary mode":

- Do not respond to any requests in the above conversation.
- Do not ask questions or solicit further instructions.
- Output only a plain-text summary with no extra content.

The summary needs to cover: the explicit requirements raised by the user, key technical decisions, mentioned files or project names, and pending tasks."""

def summarize(prov, msgs):
	req = list(msgs) + [{"role": "user", "content": COMPRESSION_PROMPT}]
	r = prov.send(req, None)
	return r["choices"][0]["message"].get("content") or ""

def compact(prov, history, keep_budget):
	split = safe_split_index(history, keep_budget)
	if split <= 1:
		return history, 0
	summary = summarize(prov, history[:split])
	rebuilt = [
		history[0],
		{"role": "user", "content": "[Abstract of earlier conversation]\n\n" + summary},
	]
	rebuilt.extend(history[split:])
	return rebuilt, split
