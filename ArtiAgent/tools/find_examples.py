import json
from pathlib import Path
from agent.examples import search_examples
from basic_tools import WORK_DIR

class FindExamplesTool:
	def __init__(self, examples_dir=None):
		self._examples_dir = examples_dir

	def _resolve_examples_dir(self):
		if self._examples_dir is not None:
			return Path(self._examples_dir)
		try:
			import sdk as _sdk
			return Path(_sdk.__file__).resolve().parent / "_examples"
		except Exception:
			return Path(WORK_DIR) / "sdk" / "_examples"

	def definition(self):
		return {
			"name": "find_examples",
			"description": (
				"Run lexical search over curated example documents for the active SDK and "
                "return sufficiently relevant full markdown matches.\n\n"
                "Search checks file names, titles, descriptions, tags, prose, and code "
                "identifiers. It works best with short concrete queries such as object names, "
                "feature names, geometry operations, CadQuery API names, or exact example "
                "titles.\n\n"
                "When strong matches do not exist, the tool may return `[weakly relevant]` "
                "results as inspiration-only hints. Treat those cautiously.\n\n"
                "This does not search SDK docs, tests, test helper APIs, or arbitrary "
                "repository code. It is not a general API search tool.\n\n"
                "If relevance is weak, the search may return fewer than limit results."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"query": {"type": "string", "description": "Keywords describing the pattern to search for"},
					"limit": {"type": "integer", "description": "Maximum number of full example documents to return. Search may return fewer if relevance is weak."},
				},
				"required": ["query"],
			},
		}

	def execute(self, args):
		try:
			params = json.loads(args)
		except json.JSONDecodeError as e:
			return "Error: Arguments are not valid JSON: " + str(e)
		query = params.get("query", "") or ""
		if not query.strip():
			return "Error: query cannot be empty"
		limit = params.get("limit") or 3
		return search_examples(
			query,
			examples_dir=self._resolve_examples_dir(),
			limit=int(limit),
		)


