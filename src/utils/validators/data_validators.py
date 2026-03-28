"""Data format and serialization validators.

Handles validation of data formats like CSV row data.
"""

import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class DataValidators:
    """Validators for data formats and serialization"""

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
