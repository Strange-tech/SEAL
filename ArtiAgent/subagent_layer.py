import os
import json
import sys
import threading
import memory
from budget import estimate_text
from registry_layer import Registry

# --- Subagent Layer ---

CHILD_MAX_ROUNDS = 6
MAX_PARALLEL_SUB_AGENTS = 4

class SubAgentTool:
	def __init__(self, provider, tools, skills):
		self.provider = provider
		self.tools = tools
		self.skills = skills

	def definition(self):
		return {
			"name": "sub_agent",
			"description": (
				"Spawn an isolated sub-agent for an independent subtask. The sub-agent has no access to prior conversation history. Use a self-contained prompt with all required information. Only the sub-agent's final result is returned; its tool calls and file reads are not propagated to your context."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"description": {"type": "string", "description": "A one-sentence label for this subtask, for logging only."},
					"prompt": {"type": "string", "description": "Full description of the subtask, self-contained — the sub-agent has no access to any other context."},
				},
				"required": ["description", "prompt"]
			},
		}

	def execute(self, args):
		try:
			in_ = json.loads(args) or {}
		except json.JSONDecodeError as e:
			return "Error: Arguments are not valid JSON: " + str(e)
		description = in_.get("description", "")
		prompt = in_.get("prompt", "")
		if not prompt.strip():
			return "Error: Prompt cannot be empty — the sub-agent has no access to other context and relies entirely on this."
		child_reg = Registry(*self.tools)
		child_history = [
            {"role": "system", "content": memory.compose_system_prompt(self.skills)},
            {"role": "user", "content": prompt},
        ]
		try:
			reply, tokens, complete = run_child_loop(self.provider, child_reg, child_history)
		except Exception as e:
			return "Error: Sub-agent execution failed:" + str(e)
		tag = "" if complete else "[Incomplete: Reached round limit. Partial results below]\n\n"
		print(f"[Sub-agent {description!r} finished: consumed approx {tokens} tokens internally, "
				f"parent conversation only receives the reply below, approx {estimate_text(reply)} tokens]", file=sys.stderr)
		return tag + reply


def run_child_loop(provider, reg, history):
	total_tokens = 0
	for _ in range(CHILD_MAX_ROUNDS):
		r = provider.send(history, reg.definitions())
		u = r.get("usage") or {}
		total_tokens += u.get("prompt_tokens", 0) + u.get("completion_tokens", 0)
		choice = r["choices"][0]
		msg = choice["message"]
		history.append(msg)
		if choice.get("finish_reason") != "tool_calls":
			return msg.get("content") or "", total_tokens, True
		for tc in msg.get("tool_calls") or []:
			result = reg.execute(tc["function"]["name"], tc["function"]["arguments"])
			history.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
	last = history[-1]
	return last.get("content") or "", total_tokens, False

def can_fan_out(calls):
	if len(calls) < 2:
		return False
	return all(tc["function"]["name"] == "sub_agent" for tc in calls)

def dispatch_tool_calls(reg, round_no, calls):
	results = [None] * len(calls)
	if can_fan_out(calls):
		sem = threading.Semaphore(MAX_PARALLEL_SUB_AGENTS)
		log_lock = threading.Lock()
		threads = []
		for i, tc in enumerate(calls):
			sem.acquire()

			def worker(i=i, tc=tc):
				try:
					with log_lock:
						print(f"[round {round_no}] {tc['function']['name']}({tc['function']['arguments']})",
						      file=sys.stderr)
					results[i] = reg.execute(tc["function"]["name"], tc["function"]["arguments"])
				finally:
					sem.release()

			t = threading.Thread(target=worker)
			threads.append(t)
			t.start()
		for t in threads:
			t.join()
	else:
		for i, tc in enumerate(calls):
			print(f"[round {round_no}] {tc['function']['name']}({tc['function']['arguments']})", file=sys.stderr)
			results[i] = reg.execute(tc["function"]["name"], tc["function"]["arguments"])
	return [{"role": "tool", "tool_call_id": tc["id"], "content": results[i]} for i, tc in enumerate(calls)]


