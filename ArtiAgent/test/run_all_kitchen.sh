#!/bin/bash
# Run ArtiAgent --box/--image on every remaining kitchen object (skips scale, already done).
cd /mnt/sda/johnli/SEAL/ArtiAgent || exit 1
source ~/miniconda3/etc/profile.d/conda.sh
conda activate layout
echo "=== run_all_kitchen start $(date) ==="
python test/test_box.py --all
echo "=== run_all_kitchen end $(date) rc=$? ==="
