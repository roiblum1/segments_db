import json
import logging
import asyncio
import os
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime
from filelock import FileLock

logger = logging.getLogger(__name__)

class JSONStorage:
    """JSON file-based storage with file locking for atomic operations"""

    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        self.data_file = self.data_dir / "segments.json"
        self.lock_file = self.data_dir / "segments.json.lock"
        self._lock = FileLock(str(self.lock_file), timeout=10)

        # Create data directory if it doesn't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize empty data file if it doesn't exist
        if not self.data_file.exists():
            self._write_data({"segments": [], "next_id": 1})
            logger.info(f"Initialized new data file at {self.data_file}")

    def _read_data(self) -> Dict[str, Any]:
        """Read data from JSON file"""
        try:
            with open(self.data_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning("Data file corrupted or missing, initializing new file")
            return {"segments": [], "next_id": 1}

    def _write_data(self, data: Dict[str, Any]) -> None:
        """Write data to JSON file atomically"""
        # Write to temporary file first
        temp_file = self.data_file.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        # Atomic rename
        temp_file.replace(self.data_file)

    async def _execute_with_lock(self, func):
        """Execute a function with file lock (runs in thread pool to avoid blocking)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func)

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single segment matching the query"""
        def _find():
            with self._lock:
                data = self._read_data()
                for segment in data["segments"]:
                    if self._matches_query(segment, query):
                        return segment.copy()
                return None

        return await self._execute_with_lock(_find)

    async def find(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find all segments matching the query"""
        def _find():
            with self._lock:
                data = self._read_data()
                results = []
                for segment in data["segments"]:
                    if self._matches_query(segment, query):
                        results.append(segment.copy())
                return results

        return await self._execute_with_lock(_find)

    async def find_one_and_update(
        self,
        query: Dict[str, Any],
        update: Dict[str, Any],
        sort: Optional[List[tuple]] = None
    ) -> Optional[Dict[str, Any]]:
        """Find a segment and update it atomically"""
        def _find_and_update():
            with self._lock:
                data = self._read_data()

                # Find matching segments
                matches = []
                for i, segment in enumerate(data["segments"]):
                    if self._matches_query(segment, query):
                        matches.append((i, segment))

                if not matches:
                    return None

                # Sort if specified
                if sort:
                    for sort_field, sort_order in reversed(sort):
                        matches.sort(
                            key=lambda x: x[1].get(sort_field, 0),
                            reverse=(sort_order == -1)
                        )

                # Update first match
                idx, segment = matches[0]
                if "$set" in update:
                    segment.update(update["$set"])

                data["segments"][idx] = segment
                self._write_data(data)

                return segment.copy()

        return await self._execute_with_lock(_find_and_update)

    async def insert_one(self, document: Dict[str, Any]) -> str:
        """Insert a new segment"""
        def _insert():
            with self._lock:
                data = self._read_data()

                # Generate new ID
                new_id = str(data["next_id"])
                data["next_id"] += 1

                # Add ID to document
                document["_id"] = new_id

                # Add to segments
                data["segments"].append(document)

                self._write_data(data)
                return new_id

        return await self._execute_with_lock(_insert)

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> int:
        """Update a single segment matching the query"""
        def _update():
            with self._lock:
                data = self._read_data()
                modified = 0

                for segment in data["segments"]:
                    if self._matches_query(segment, query):
                        if "$set" in update:
                            segment.update(update["$set"])
                        modified = 1
                        break

                if modified:
                    self._write_data(data)

                return modified

        return await self._execute_with_lock(_update)

    async def delete_one(self, query: Dict[str, Any]) -> int:
        """Delete a single segment matching the query"""
        def _delete():
            with self._lock:
                data = self._read_data()
                deleted = 0

                for i, segment in enumerate(data["segments"]):
                    if self._matches_query(segment, query):
                        data["segments"].pop(i)
                        deleted = 1
                        break

                if deleted:
                    self._write_data(data)

                return deleted

        return await self._execute_with_lock(_delete)

    async def count_documents(self, query: Dict[str, Any]) -> int:
        """Count segments matching the query"""
        def _count():
            with self._lock:
                data = self._read_data()
                count = 0
                for segment in data["segments"]:
                    if self._matches_query(segment, query):
                        count += 1
                return count

        return await self._execute_with_lock(_count)

    def _matches_query(self, document: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if document matches query"""
        for key, value in query.items():
            if key == "$or":
                # Handle $or operator
                if not any(self._matches_query(document, condition) for condition in value):
                    return False
            elif isinstance(value, dict):
                # Handle operators
                if "$ne" in value:
                    if document.get(key) == value["$ne"]:
                        return False
                elif "$regex" in value:
                    import re
                    pattern = value["$regex"]
                    options = value.get("$options", "")
                    flags = re.IGNORECASE if "i" in options else 0
                    doc_value = str(document.get(key, ""))
                    if not re.search(pattern, doc_value, flags):
                        return False
                else:
                    # Unknown operator, compare directly
                    if document.get(key) != value:
                        return False
            else:
                # Direct comparison
                if document.get(key) != value:
                    return False
        return True


# Global storage instance
_storage: Optional[JSONStorage] = None


def get_storage() -> JSONStorage:
    """Get the global storage instance"""
    global _storage
    if _storage is None:
        data_dir = os.getenv("DATA_DIR", "/app/data")
        _storage = JSONStorage(data_dir)
        logger.info(f"Initialized JSON storage at {data_dir}")
    return _storage


async def init_storage():
    """Initialize storage (creates indexes in MongoDB equivalent)"""
    storage = get_storage()
    logger.info("JSON storage initialized successfully")
    # Note: JSON storage doesn't need indexes, but we keep this for compatibility


async def close_storage():
    """Close storage connection (no-op for JSON)"""
    logger.info("JSON storage closed")
