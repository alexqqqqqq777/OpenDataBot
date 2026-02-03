#!/usr/bin/env python3
"""
Sync Worksection case numbers to GitHub Gist.
This script runs in GitHub Actions and updates a Gist with case numbers.
The VPS bot reads from this Gist instead of accessing Worksection directly.
"""

import os
import re
import json
import hashlib
from datetime import datetime
import httpx

# Worksection settings
WORKSECTION_DOMAIN = os.environ.get('WORKSECTION_DOMAIN')
WORKSECTION_API_KEY = os.environ.get('WORKSECTION_API_KEY')

# GitHub Gist settings
GIST_ID = os.environ.get('GIST_ID')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')

# Case number pattern (same as in bot)
CASE_PATTERN = r'(\d{3,4}/\d+/\d{2}(?:-[а-яіїєґ]+)?)'


def generate_hash(query_params: str, api_key: str) -> str:
    """Generate MD5 hash for Worksection API authentication."""
    data = query_params + api_key
    return hashlib.md5(data.encode()).hexdigest()


def extract_case_numbers(text: str) -> list:
    """Extract all case numbers from text."""
    if not text:
        return []
    matches = re.findall(CASE_PATTERN, text, re.IGNORECASE)
    # Deduplicate while preserving order
    seen = set()
    result = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


async def fetch_worksection_tasks() -> list:
    """Fetch all tasks from Worksection."""
    # Use v2 API endpoint
    base_url = f"https://{WORKSECTION_DOMAIN}/api/admin/v2/"
    action = "get_all_tasks"
    params = {"extra": "text"}
    
    # Build hash query - action first, then sorted params
    hash_parts = [f"action={action}"]
    for key in sorted(params.keys()):
        hash_parts.append(f"{key}={params[key]}")
    hash_query = "&".join(hash_parts)
    hash_value = generate_hash(hash_query, WORKSECTION_API_KEY)
    
    # URL format: base?action=X&param=Y&hash=Z
    url = f"{base_url}?{hash_query}&hash={hash_value}"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') != 'ok':
            raise Exception(f"Worksection API error: {data}")
        
        return data.get('data', [])


async def update_gist(case_numbers: list) -> None:
    """Update GitHub Gist with case numbers."""
    url = f"https://api.github.com/gists/{GIST_ID}"
    
    content = {
        "case_numbers": case_numbers,
        "count": len(case_numbers),
        "updated_at": datetime.utcnow().isoformat() + "Z"
    }
    
    payload = {
        "files": {
            "worksection_cases.json": {
                "content": json.dumps(content, ensure_ascii=False, indent=2)
            }
        }
    }
    
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.patch(url, json=payload, headers=headers)
        response.raise_for_status()
        print(f"Gist updated successfully: {len(case_numbers)} case numbers")


async def main():
    """Main sync function."""
    # Validate environment
    if not all([WORKSECTION_DOMAIN, WORKSECTION_API_KEY, GIST_ID, GITHUB_TOKEN]):
        missing = []
        if not WORKSECTION_DOMAIN:
            missing.append("WORKSECTION_DOMAIN")
        if not WORKSECTION_API_KEY:
            missing.append("WORKSECTION_API_KEY")
        if not GIST_ID:
            missing.append("GIST_ID")
        if not GITHUB_TOKEN:
            missing.append("GITHUB_TOKEN")
        raise ValueError(f"Missing environment variables: {', '.join(missing)}")
    
    print(f"Fetching tasks from Worksection ({WORKSECTION_DOMAIN})...")
    tasks = await fetch_worksection_tasks()
    print(f"Fetched {len(tasks)} tasks")
    
    # Extract case numbers from task names
    all_case_numbers = set()
    for task in tasks:
        task_name = task.get('name', '')
        case_numbers = extract_case_numbers(task_name)
        all_case_numbers.update(case_numbers)
    
    case_list = sorted(list(all_case_numbers))
    print(f"Extracted {len(case_list)} unique case numbers")
    
    # Update Gist
    await update_gist(case_list)
    print("Sync completed successfully!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
