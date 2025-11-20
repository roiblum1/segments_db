"""Data format and serialization validators.

Handles validation of data formats like JSON serialization, timezone-aware datetimes,
CSV row data, and update data structures.
"""

import logging
import json
import ipaddress
from typing import Dict, Any
from datetime import datetime, date
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class DataValidators:
    """Validators for data formats and serialization"""

    @staticmethod
    def validate_update_data(update_data: Dict[str, Any]) -> None:
        """Validate bulk update data to ensure no malicious content"""
        from .input_validators import InputValidators

        # Check for empty updates
        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="Update data cannot be empty"
            )

        # Validate individual fields if present
        if "vlan_id" in update_data:
            InputValidators.validate_vlan_id(update_data["vlan_id"])

        if "epg_name" in update_data:
            InputValidators.validate_epg_name(update_data["epg_name"])

        if "cluster_name" in update_data and update_data["cluster_name"]:
            InputValidators.validate_cluster_name(update_data["cluster_name"])

        if "description" in update_data:
            InputValidators.validate_description(update_data["description"])

        if "segment" in update_data:
            # Basic format validation (full validation requires site context)
            try:
                ipaddress.ip_network(update_data["segment"], strict=False)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid segment format: {update_data['segment']}"
                )

        # Check for suspicious keys that shouldn't be updated directly
        forbidden_keys = ["_id", "id", "created_at", "__proto__", "constructor"]
        for key in update_data.keys():
            if key in forbidden_keys:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot update protected field: {key}"
                )

            # Check for potential NoSQL injection patterns in keys
            if "$" in key or "." in key:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid field name: {key}"
                )

        logger.debug("Update data validation passed")

    @staticmethod
    def validate_timezone_aware_datetime(dt_value: Any) -> None:
        """Validate that datetime is timezone-aware to prevent timezone bugs"""
        if dt_value is None:
            return

        if not isinstance(dt_value, datetime):
            raise HTTPException(
                status_code=400,
                detail=f"Expected datetime object, got {type(dt_value).__name__}"
            )

        if dt_value.tzinfo is None:
            raise HTTPException(
                status_code=400,
                detail="Datetime must be timezone-aware. Use datetime.now(timezone.utc)"
            )

        logger.debug("Datetime timezone validation passed")

    @staticmethod
    def validate_json_serializable(data: Any, field_name: str = "data") -> None:
        """
        Validate that data can be JSON serialized
        Prevents issues with datetime, bytes, custom objects
        """
        # Check for types that aren't natively JSON serializable
        # and shouldn't be converted to strings
        if hasattr(data, '__dict__') and not isinstance(data, (dict, list, str, int, float, bool, type(None))):
            logger.error(f"JSON serialization failed for {field_name}: custom object {type(data)}")
            raise HTTPException(
                status_code=400,
                detail=f"Field '{field_name}' contains non-serializable custom object: {type(data).__name__}"
            )

        try:
            # Try to serialize without default handler first (strict check)
            json.dumps(data)
        except (TypeError, ValueError) as e:
            # Check if it's a datetime (acceptable with default handler)
            if isinstance(data, (datetime, date)):
                # Datetime is acceptable - can be serialized with default=str
                pass
            else:
                logger.error(f"JSON serialization failed for {field_name}: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Field '{field_name}' contains non-serializable data: {str(e)}"
                )

        logger.debug(f"JSON serialization validation passed for {field_name}")

    @staticmethod
    def validate_csv_row_data(row_data: dict, row_number: int) -> None:
        """
        Validate CSV import row data

        Args:
            row_data: Dictionary of row data
            row_number: Row number for error reporting
        """
        from .input_validators import InputValidators

        required_fields = ['site', 'vlan_id', 'epg_name', 'segment']

        # Check required fields
        missing_fields = [field for field in required_fields if not row_data.get(field)]
        if missing_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Row {row_number}: Missing required fields: {', '.join(missing_fields)}"
            )

        # Validate vlan_id is numeric
        try:
            vlan_id = int(row_data['vlan_id'])
            InputValidators.validate_vlan_id(vlan_id)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail=f"Row {row_number}: Invalid VLAN ID '{row_data.get('vlan_id')}' - must be integer between 1-4094"
            )

        # Validate other fields
        InputValidators.validate_epg_name(row_data['epg_name'])
        InputValidators.validate_site(row_data['site'])

        # Validate description if present
        if row_data.get('description'):
            InputValidators.validate_description(row_data['description'])

        logger.debug(f"CSV row {row_number} validation passed")
