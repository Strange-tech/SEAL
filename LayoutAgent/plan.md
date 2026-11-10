# Layout-Agent

Purpose: reconstruct an indoor layout based on the user's request.

Input: a single-frame image.

Output: room.py, structured as a scene graph, including nodes and edges. A node is an object OBB (including walls, floors, etc.). Edges include the following relations: embedded (a door/window inside a wall), adjacent (horizontal relation, a small gap allowed), abuts (a constrained horizontal/vertical relation, e.g. a cup on a table), allowed overlap (e.g. a chair tucked under a table — the OBBs intersect but it is allowed). Include only visible objects.

Design idea: derived from ex-articraft, an agent that generates articulated objects (Arti-Agent), whose input is also text/image and whose output is model.py.
Arti-Agent uses the cadquery library and wrote a whole SDK, including basic geometry objects, collision/floating detection, URDF export, and articulated-object objects. This SDK can be seen as a further encapsulation of cadquery, simplifying the originally complex implementation into a number of objects or functions. The SDK's role is to fit the LLM's understanding and writing, and to return concrete success or error messages so the LLM can easily modify.
In addition, Arti-Agent has a set of function tools: besides basic read/write/edit file, there are compile (compile the model for Quality Check, identifying floating/overlap issues, etc.) and probe (probe the details of each part of the model, e.g. bounding box, position, and other data).
Furthermore, Arti-Agent has rich prompt engineering, including docs, system prompt, etc. These priors are read by the agent before it starts writing model.py, so the agent writes both fast and well.

Composition: Layout-Agent needs prompt engineering, tools, and an SDK. Besides basic file read/write, the tools also need: 1. SAM3 image segmentation (verified to exist) 2. Depth Anything 3 reconstruction — it does not need real meters; even if the scale does not match reality, correct relative relations are enough (verified to exist) 3. build a custom East/North basis and project the scene onto the custom basis 4. a compile tool that detects whether object OBBs collide or float, etc. (embedded and overlap relations can be exempt). The SDK needs OBB detection and a series of other tools to support the tools. Prompt engineering includes the basic system prompt.

Flow:
1. Given an image, feed it to a VLM and return text: the object names in the scene and their relative/absolute positions in the frame (only as an aid; the reconstructed values are the focus later).
2. The VLM calls tool SAM3 based on the object names to get each object's image mask under frame_ID.
3. The VLM calls tool DA3 based on the images to get the whole-scene points + camera ex/intrinsic + frame depth.
4. The VLM uses each object's image mask under frame_ID and the frame depth to backproject each object's points in the scene.
5. Get an OBB bounding box (center position, orientation, scale) for each object's points.
5.5 Use the detected wall/floor OBBs to estimate the dominant directions, establish the East/North world frame, and snap the wall/door/window/object orientations to that orthogonal frame (Manhattan regularization).
6. Write room.py (code, not a JSON object).
7. Call tool compile to check room.py until failure, warning, note are all zero (referencing ex-articraft; the judgment is defined in the SDK).
