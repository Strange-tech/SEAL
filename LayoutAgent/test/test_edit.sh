#!/usr/bin/env bash
# LayoutAgent incremental edit smoke test.
# Each edit forks the PREVIOUS edit's record (not the base record), so edits chain.
# Each edit result is exported to LayoutAgent/output/edit_*.json.
# Run from LayoutAgent/test/ (or anywhere) with the `layout` conda env active.
# NOTE: do NOT run as-is unless you intend to launch 10 sequential LLM edits.
set -euo pipefail
cd "$(dirname "$0")/.."   # LayoutAgent root (main.py / room.py live here)

BASE_ROOM_ID="rec_generate-a-room-with-a-sofa-2-tables-4-chairs-an_20261117_055648_396108_3c47e8a4"
OUT="output"

# run_edit <parent_record_id> <task> <emit_json_path>  -> echoes the NEW record id
run_edit() {
    local parent="$1" task="$2" out="$3"
    local log rid
    log=$(python main.py --edit "$parent" --task "$task" --emit-scene-graph "$out" 2>&1)
    rid=$(sed -n 's/.*\[record\] \(rec_[a-zA-Z0-9_-]*\).*/\1/p' <<< "$log" | head -1)
    echo "$rid"
}

# --- incremental chain ---
R1=$(run_edit "$BASE_ROOM_ID" "add a floor lamp next to the sofa" "$OUT/edit_add_floor_lamp.json")
echo "edit 1 -> $R1"

R2=$(run_edit "$R1" "add a side table next to the sofa" "$OUT/edit_add_side_table.json")
echo "edit 2 -> $R2"

R3=$(run_edit "$R2" "add a window on the left wall" "$OUT/edit_add_window.json")
echo "edit 3 -> $R3"

R4=$(run_edit "$R3" "remove the coffee table" "$OUT/edit_remove_coffee_table.json")
echo "edit 4 -> $R4"

R5=$(run_edit "$R4" "delete one of the dining chairs" "$OUT/edit_delete_chair.json")
echo "edit 5 -> $R5"

R6=$(run_edit "$R5" "remove the TV stand" "$OUT/edit_remove_tv_stand.json")
echo "edit 6 -> $R6"

R7=$(run_edit "$R6" "move the sofa to the left wall" "$OUT/edit_move_sofa.json")
echo "edit 7 -> $R7"

R8=$(run_edit "$R7" "move the TV to the back wall" "$OUT/edit_move_tv.json")
echo "edit 8 -> $R8"

R9=$(run_edit "$R8" "move the dining table and all chairs to the center of the room" "$OUT/edit_move_dining_table.json")
echo "edit 9 -> $R9"

R10=$(run_edit "$R9" "swap the sofa and the TV, then add a floor lamp next to the new sofa position" "$OUT/edit_combined.json")
echo "edit 10 -> $R10"
