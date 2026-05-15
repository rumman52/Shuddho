# Optional sentence-level corrector checkpoint

This directory is for the optional sentence-level corrector checkpoint.
Do not commit large binary checkpoints directly unless using Git LFS correctly.
For Render production, prefer external model storage such as Hugging Face Hub, S3, Cloudflare R2, or GitHub Releases.

The backend runs in degraded rules + spelling mode when `best_model.pt` is missing.
