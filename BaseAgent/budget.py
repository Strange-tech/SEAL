import os
import sys
import json
import time
import secrets
from datetime import datetime

BUDGET_FRACTION = 0.75

# --- Budget Layer ---

# The budget layer maintains the session context. 
# The main loop decides whether to trigger compression based 
# on the length of the context.

def context_window(model):
	m = model.lower()
	if 'deepseek' in m:
		return 1_000_000
	if 'gpt-4' in m:
		return 128_000
	if 'claude' in m:
		return 200_000
	return 128_000

def effective_context_window(model):
	v = os.environ.get("CONTEXT_WINDOW", "")
	if v:
		try:
			n = int(v)
		except ValueError:
			n = 0
		if n > 0:
			return n
	return context_window(model)

def check_budget(used_tokens, window):
	pct = used_tokens / window * 100
	print(f"[Budget {used_tokens}/{window} tokens, {pct:.1f}%]", file=sys.stderr)
	over = used_tokens >= window * BUDGET_FRACTION
	if over:
		print(f"⚠️ Window usage at {pct:.0f}%, nearing limit — consider freeing up space.", file=sys.stderr)
	return over

def estimate_tokens(msgs):
	total = 0
	for m in msgs:
		total += estimate_text(m.get("content") or "")
		for tc in m.get("tool_calls") or []:
			total += estimate_text(tc["function"]["name"]) + estimate_text(tc["function"]["arguments"])
	return total

def estimate_text(s):
	if s is None:
		return 0
	if isinstance(s, str):
		ascii_count, multi = 0, 0
		for ch in s:
			if ord(ch) < 128:
				ascii_count += 1
			else:
				multi += len(ch.encode("utf-8"))
		return ascii_count // 4 + int(multi / 1.5 + 0.5)
	if isinstance(s, dict):
		return estimate_text(s.get("text") or s.get("content") or "")
	if isinstance(s, (list, tuple)):
		total = 0
		for part in s:
			if isinstance(part, dict):
				total += estimate_text(part.get("text") or part.get("content"))
			elif isinstance(part, str):
				total += estimate_text(part)
		return total
	return 0
