#!/usr/bin/env python3
"""
Entry point for Court Monitoring Bot
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.main import main

if __name__ == "__main__":
    asyncio.run(main())
