"""manhattan_regularize tool: snap scene-graph node orientations to the Manhattan orthogonal basis.

(The file read/write functionality of the old fileio.py has been taken over by basic_tools.py; this file is reused as a node-level geometry tool.)
"""

import json

from sdk.manhattan import manhattan_regularize_nodes


class ManhattanRegularizeTool:
    """LLM tool: Manhattan-regularize nodes and return the new node list (JSON)."""

    def definition(self):
        return {
            "name": "manhattan_regularize",
            "description": (
                "Snap node orientations (theta[1] yaw) to the East/North Manhattan basis derived "
                "from the wall/floor directions. Takes the scene-graph node list as JSON and "
                "returns the regularized node list as JSON."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "array",
                        "description": "Scene-graph node list; each node {\"id\",\"type\",\"C\",\"D\",\"theta\"}",
                    },
                    "angle_threshold": {
                        "type": "number",
                        "description": "Max angle (deg) from a grid direction to snap (default 15)",
                    },
                },
                "required": ["nodes"],
            },
        }

    def execute(self, args):
        try:
            params = json.loads(args)
        except json.JSONDecodeError as e:
            return "Error: Arguments are not valid JSON: " + str(e)
        nodes = params.get("nodes")
        if not isinstance(nodes, list):
            return "Error: nodes must be a JSON array"
        try:
            threshold = float(params.get("angle_threshold", 15.0))
        except (TypeError, ValueError):
            return "Error: angle_threshold must be a number"
        try:
            out = manhattan_regularize_nodes(nodes, angle_threshold=threshold)
        except Exception as e:
            return "Error: manhattan_regularize failed: " + str(e)
        return json.dumps(out, ensure_ascii=False, indent=2)
