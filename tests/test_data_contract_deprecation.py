"""Tests for data contract deprecation tracker."""

import pytest
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from app.infra.data_contract_deprecation import (
    DataContractDeprecationTracker,
    DataContract,
    DeprecatedField,
    BreakingChange,
    BreakingChangeType,
    SeverityLevel,
    CompatibilityCheckResult,
)


@pytest.fixture
def temp_registry():
    """Create temporary registry directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def tracker(temp_registry):
    """Create tracker instance with temp registry."""
    return DataContractDeprecationTracker(registry_dir=temp_registry)


class TestDataContract:
    """Test DataContract model."""
    
    def test_create_contract(self):
        """Test creating a data contract."""
        contract = DataContract(table_name="users")
        assert contract.table_name == "users"
        assert contract.version == "1.0"
        assert contract.minimum_retention_period_days == 90
        assert contract.deprecated_fields == []
    
    def test_contract_to_dict(self):
        """Test contract serialization."""
        contract = DataContract(table_name="users")
        data = contract.to_dict()
        assert data["table_name"] == "users"
        assert data["version"] == "1.0"
        assert "created_at" in data
    
    def test_contract_from_dict(self):
        """Test contract deserialization."""
        data = {
            "table_name": "users",
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "deprecated_fields": [],
            "minimum_retention_period_days": 90,
        }
        contract = DataContract.from_dict(data)
        assert contract.table_name == "users"
        assert contract.version == "1.0"


class TestDeprecatedField:
    """Test DeprecatedField model."""
    
    def test_create_deprecated_field(self):
        """Test creating deprecated field."""
        removal_date = (datetime.now() + timedelta(days=90)).isoformat()
        field = DeprecatedField(
            field_name="phone",
            deprecated_at=datetime.now().isoformat(),
            removal_target=removal_date,
            reason="Moved to user_contacts",
            replacement="user_contacts.phone"
        )
        assert field.field_name == "phone"
        assert field.reason == "Moved to user_contacts"
    
    def test_days_until_removal(self):
        """Test calculating days until removal."""
        removal_date = (datetime.now() + timedelta(days=30)).isoformat()
        field = DeprecatedField(
            field_name="phone",
            deprecated_at=datetime.now().isoformat(),
            removal_target=removal_date,
            reason="Test"
        )
        days = field.days_until_removal()
        assert 29 <= days <= 30  # Account for time passing during execution
    
    def test_is_removal_overdue(self):
        """Test checking if removal is overdue."""
        past_date = (datetime.now() - timedelta(days=1)).isoformat()
        field = DeprecatedField(
            field_name="phone",
            deprecated_at=datetime.now().isoformat(),
            removal_target=past_date,
            reason="Test"
        )
        assert field.is_removal_overdue() is True
    
    def test_is_removal_not_overdue(self):
        """Test checking if removal is not overdue."""
        future_date = (datetime.now() + timedelta(days=30)).isoformat()
        field = DeprecatedField(
            field_name="phone",
            deprecated_at=datetime.now().isoformat(),
            removal_target=future_date,
            reason="Test"
        )
        assert field.is_removal_overdue() is False


class TestBreakingChange:
    """Test BreakingChange model."""
    
    def test_create_breaking_change(self):
        """Test creating breaking change."""
        change = BreakingChange(
            change_type=BreakingChangeType.REMOVED_COLUMN,
            field_name="phone",
            severity=SeverityLevel.CRITICAL,
            description="Column removed without deprecation"
        )
        assert change.field_name == "phone"
        assert change.severity == SeverityLevel.CRITICAL
    
    def test_breaking_change_to_dict(self):
        """Test serialization."""
        change = BreakingChange(
            change_type=BreakingChangeType.TYPE_CHANGE,
            field_name="age",
            severity=SeverityLevel.HIGH,
            description="Type changed",
            old_definition="INTEGER",
            new_definition="VARCHAR"
        )
        data = change.to_dict()
        assert data["type"] == "type_change"
        assert data["field"] == "age"
        assert data["severity"] == "high"


class TestDataContractDeprecationTracker:
    """Test tracker functionality."""
    
    def test_register_contract(self, tracker):
        """Test registering a new contract."""
        contract = tracker.register_contract("users")
        assert contract.table_name == "users"
        assert "users" in tracker.contracts
    
    def test_register_duplicate_contract(self, tracker):
        """Test handling duplicate registration."""
        tracker.register_contract("users")
        contract2 = tracker.register_contract("users")
        assert len([c for c in tracker.contracts if c == "users"]) == 1
    
    def test_save_and_load_contracts(self, temp_registry):
        """Test persistence."""
        tracker1 = DataContractDeprecationTracker(registry_dir=temp_registry)
        tracker1.register_contract("users")
        
        # Create new tracker instance - should load saved contracts
        tracker2 = DataContractDeprecationTracker(registry_dir=temp_registry)
        assert "users" in tracker2.contracts
    
    def test_mark_field_deprecated(self, tracker):
        """Test marking field for deprecation."""
        tracker.register_contract("users")
        removal_date = (datetime.now() + timedelta(days=90)).isoformat()
        
        success = tracker.mark_field_deprecated(
            table_name="users",
            field_name="phone",
            removal_date=removal_date,
            reason="Moved to user_contacts",
            replacement="user_contacts.phone"
        )
        assert success is True
        assert len(tracker.contracts["users"].deprecated_fields) == 1
    
    def test_mark_field_deprecated_without_contract(self, tracker):
        """Test deprecating field without contract."""
        removal_date = (datetime.now() + timedelta(days=90)).isoformat()
        success = tracker.mark_field_deprecated(
            table_name="users",
            field_name="phone",
            removal_date=removal_date,
            reason="Test"
        )
        assert success is False
    
    def test_mark_field_deprecated_with_past_date(self, tracker):
        """Test rejecting past removal date."""
        tracker.register_contract("users")
        past_date = (datetime.now() - timedelta(days=1)).isoformat()
        
        success = tracker.mark_field_deprecated(
            table_name="users",
            field_name="phone",
            removal_date=past_date,
            reason="Test"
        )
        assert success is False
    
    def test_mark_field_deprecated_with_insufficient_retention(self, tracker):
        """Test rejecting removal date too soon."""
        tracker.register_contract("users", minimum_retention_days=90)
        too_soon = (datetime.now() + timedelta(days=30)).isoformat()
        
        success = tracker.mark_field_deprecated(
            table_name="users",
            field_name="phone",
            removal_date=too_soon,
            reason="Test"
        )
        assert success is False
    
    def test_mark_field_deprecated_duplicate(self, tracker):
        """Test preventing duplicate deprecations."""
        tracker.register_contract("users")
        removal_date = (datetime.now() + timedelta(days=90)).isoformat()
        
        tracker.mark_field_deprecated(
            table_name="users",
            field_name="phone",
            removal_date=removal_date,
            reason="First"
        )
        
        success = tracker.mark_field_deprecated(
            table_name="users",
            field_name="phone",
            removal_date=removal_date,
            reason="Second"
        )
        assert success is False
    
    def test_detect_breaking_changes_removed_field(self, tracker):
        """Test detecting removed field."""
        old_fields = {"id": "INTEGER", "phone": "VARCHAR"}
        new_fields = {"id": "INTEGER"}
        
        changes = tracker.detect_breaking_changes("users", old_fields, new_fields)
        assert len(changes) == 1
        assert changes[0].change_type == BreakingChangeType.REMOVED_COLUMN
    
    def test_detect_breaking_changes_type_change(self, tracker):
        """Test detecting type change."""
        old_fields = {"id": "INTEGER", "age": "INTEGER"}
        new_fields = {"id": "INTEGER", "age": "VARCHAR"}
        
        changes = tracker.detect_breaking_changes("users", old_fields, new_fields)
        type_changes = [c for c in changes if c.change_type == BreakingChangeType.TYPE_CHANGE]
        assert len(type_changes) == 1
    
    def test_detect_breaking_changes_with_deprecation(self, tracker):
        """Test that deprecated field removal doesn't trigger breaking change."""
        tracker.register_contract("users")
        removal_date = (datetime.now() + timedelta(days=90)).isoformat()
        tracker.mark_field_deprecated(
            table_name="users",
            field_name="phone",
            removal_date=removal_date,
            reason="Deprecated"
        )
        
        old_fields = {"id": "INTEGER", "phone": "VARCHAR"}
        new_fields = {"id": "INTEGER"}
        
        changes = tracker.detect_breaking_changes("users", old_fields, new_fields)
        # Should not detect as breaking change if properly deprecated
        removed_changes = [c for c in changes if c.change_type == BreakingChangeType.REMOVED_COLUMN]
        assert len(removed_changes) == 0
    
    def test_validate_migration_success(self, tracker):
        """Test successful migration validation."""
        tracker.register_contract("users")
        new_fields = {"id": "INTEGER", "name": "VARCHAR"}
        
        result = tracker.validate_migration("users", new_fields)
        assert result.passed is True
    
    def test_validate_migration_premature_removal(self, tracker):
        """Test blocking premature field removal."""
        tracker.register_contract("users")
        removal_date = (datetime.now() + timedelta(days=90)).isoformat()
        tracker.mark_field_deprecated(
            table_name="users",
            field_name="phone",
            removal_date=removal_date,
            reason="Deprecated"
        )
        
        new_fields = {"id": "INTEGER"}  # phone removed before removal date
        
        result = tracker.validate_migration("users", new_fields)
        assert result.passed is False
        assert len(result.breaking_changes) > 0
    
    def test_validate_migration_allowed_removal(self, tracker):
        """Test allowing removal after deadline."""
        tracker.register_contract("users")
        past_date = (datetime.now() - timedelta(days=1)).isoformat()
        
        # Manually create deprecated field with past removal date
        field = DeprecatedField(
            field_name="phone",
            deprecated_at=datetime.now().isoformat(),
            removal_target=past_date,
            reason="Deprecated"
        )
        tracker.contracts["users"].deprecated_fields.append(field)
        
        new_fields = {"id": "INTEGER"}
        
        result = tracker.validate_migration("users", new_fields)
        assert result.passed is True
    
    def test_get_deprecation_timeline(self, tracker):
        """Test getting deprecation timeline."""
        tracker.register_contract("users")
        removal_date = (datetime.now() + timedelta(days=90)).isoformat()
        tracker.mark_field_deprecated(
            table_name="users",
            field_name="phone",
            removal_date=removal_date,
            reason="Deprecated",
            replacement="user_contacts.phone"
        )
        
        timeline = tracker.get_deprecation_timeline("users")
        assert timeline["table"] == "users"
        assert len(timeline["in_progress"]) == 1
        assert timeline["in_progress"][0]["field"] == "phone"
    
    def test_get_deprecation_timeline_no_contract(self, tracker):
        """Test timeline for non-existent contract."""
        timeline = tracker.get_deprecation_timeline("users")
        assert timeline["status"] == "no_contract"
    
    def test_generate_compatibility_report(self, tracker):
        """Test generating system report."""
        tracker.register_contract("users")
        removal_date = (datetime.now() + timedelta(days=30)).isoformat()
        tracker.mark_field_deprecated(
            table_name="users",
            field_name="phone",
            removal_date=removal_date,
            reason="Deprecated"
        )
        
        report = tracker.generate_compatibility_report()
        assert report["total_contracts"] == 1
        assert report["tables_with_deprecations"] == 1
        assert len(report["reminders_30_day"]) > 0
    
    def test_multiple_contracts(self, tracker):
        """Test managing multiple contracts."""
        tracker.register_contract("users")
        tracker.register_contract("posts")
        
        assert len(tracker.contracts) == 2
    
    def test_multiple_deprecated_fields(self, tracker):
        """Test multiple deprecations per table."""
        tracker.register_contract("users")
        removal_date = (datetime.now() + timedelta(days=90)).isoformat()
        
        tracker.mark_field_deprecated(
            table_name="users",
            field_name="phone",
            removal_date=removal_date,
            reason="Deprecated"
        )
        tracker.mark_field_deprecated(
            table_name="users",
            field_name="legacy_id",
            removal_date=removal_date,
            reason="Deprecated"
        )
        
        assert len(tracker.contracts["users"].deprecated_fields) == 2
    
    def test_custom_retention_period(self, tracker):
        """Test custom retention period."""
        contract = tracker.register_contract("users", minimum_retention_days=180)
        assert contract.minimum_retention_period_days == 180
    
    def test_breaking_change_multiple_types(self, tracker):
        """Test detecting multiple breaking changes."""
        old_fields = {
            "id": "INTEGER",
            "name": "VARCHAR",
            "age": "INTEGER",
            "phone": "VARCHAR"
        }
        new_fields = {
            "id": "INTEGER",
            "name": "VARCHAR(50)",  # Type change
            "age": "VARCHAR"  # Type change
            # phone removed
        }
        
        changes = tracker.detect_breaking_changes("users", old_fields, new_fields)
        assert len(changes) >= 2


class TestCompatibilityCheckResult:
    """Test result model."""
    
    def test_create_result(self):
        """Test creating result."""
        result = CompatibilityCheckResult(passed=True)
        assert result.passed is True
        assert result.breaking_changes == []
    
    def test_result_to_dict(self):
        """Test serialization."""
        result = CompatibilityCheckResult(
            passed=False,
            warnings=["Test warning"]
        )
        data = result.to_dict()
        assert data["passed"] is False
        assert "Test warning" in data["warnings"]


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_schema(self, tracker):
        """Test with empty schema."""
        tracker.register_contract("users")
        result = tracker.validate_migration("users", {})
        assert result.passed is True
    
    def test_null_replacement(self, tracker):
        """Test deprecated field without replacement."""
        tracker.register_contract("users")
        removal_date = (datetime.now() + timedelta(days=90)).isoformat()
        
        success = tracker.mark_field_deprecated(
            table_name="users",
            field_name="legacy_field",
            removal_date=removal_date,
            reason="Deprecated"
        )
        assert success is True
    
    def test_registry_with_missing_file(self):
        """Test loading non-existent registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = DataContractDeprecationTracker(registry_dir=tmpdir)
            # Should create empty contracts dict
            assert len(tracker.contracts) == 0
    
    def test_corrupted_registry_recovery(self):
        """Test recovery from corrupted registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_file = Path(tmpdir) / "data_contracts.json"
            # Write invalid JSON
            registry_file.write_text("{invalid json")
            
            # Tracker should handle gracefully
            tracker = DataContractDeprecationTracker(registry_dir=tmpdir)
            assert isinstance(tracker.contracts, dict)
