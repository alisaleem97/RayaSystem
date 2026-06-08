# upload_to_hf.py
# ===================================================================
# Helper script to upload NexLab to Hugging Face Spaces.
# Bypasses Git to avoid committing large executables like NexPrint.exe.
# ===================================================================

import os
import sys

def upload():
    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("huggingface_hub library is not installed.")
        print("Installing it now via pip...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
        from huggingface_hub import HfApi

    # Ask the user for their token if not already stored
    print("\n--- Hugging Face Spaces Direct Uploader ---")
    token = input("Enter your Hugging Face Write Token: ").strip()
    if not token:
        print("❌ Token is required. You can get one from: https://huggingface.co/settings/tokens")
        return

    repo_id = "alisaleem97/NexLab_System"
    print(f"Uploading files to Space: {repo_id}...")

    api = HfApi()
    
    # Ignore patterns to skip local virtual environments, large files, and Git history
    ignore_patterns = [
        "print_client/**",
        ".git/**",
        "venv/**",
        ".env",
        "**/*.log",
        "**/__pycache__/**",
        "backups/**",
        "tmp/**",
        "NexLab_Published/**"
    ]

    try:
        api.upload_folder(
            folder_path=".",
            repo_id=repo_id,
            repo_type="space",
            token=token,
            ignore_patterns=ignore_patterns
        )
        print("\n🎉 Upload Completed Successfully!")
        print("Your Space will now build and start automatically.")
        print(f"Visit it at: https://huggingface.co/spaces/{repo_id}")
    except Exception as e:
        print(f"\n❌ Error during upload: {e}")

if __name__ == "__main__":
    upload()
