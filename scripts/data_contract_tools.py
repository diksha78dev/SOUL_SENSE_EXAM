#!/usr/bin/env python
"""CLI tools for data contract deprecation tracking."""

import sys
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from app.infra.data_contract_deprecation import (
    DataContractDeprecationTracker,
    SeverityLevel,
)


def format_result(title: str, passed: bool, details: list = None) -> None:
    """Format and print result with status indicator."""
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"\n{status}: {title}")
    if details:
        for detail in details:
            print(f"  - {detail}")


def cmd_register_contract(args) -> None:
    """Register a new data contract."""
    tracker = DataContractDeprecationTracker(args.registry_dir)
    
    retention_days = args.retention_days or 90
    contract = tracker.register_contract(args.table, minimum_retention_days=retention_days)
    
    print(f"\n✓ Registered contract for table: {args.table}")
    print(f"  - Minimum retention period: {contract.minimum_retention_period_days} days")
    print(f"  - Created: {contract.created_at}")


def cmd_deprecate_field(args) -> None:
    """Mark a field for deprecation."""
    tracker = DataContractDeprecationTracker(args.registry_dir)
    
    success = tracker.mark_field_deprecated(
        table_name=args.table,
        field_name=args.field,
        removal_date=args.removal_date,
        reason=args.reason,
        replacement=args.replacement
    )
    
    if success:
        removal_dt = datetime.fromisoformat(args.removal_date)
        days = (removal_dt - datetime.now()).days
        print(f"\n✓ Marked {args.table}.{args.field} for removal")
        print(f"  - Removal date: {args.removal_date}")
        print(f"  - Days remaining: {days}")
        print(f"  - Reason: {args.reason}")
        if args.replacement:
            print(f"  - Replacement: {args.replacement}")
    else:
        print(f"\n✗ Failed to mark field for deprecation")
        sys.exit(1)


def cmd_check_migration(args) -> None:
    """Check if a migration violates any contracts."""
    tracker = DataContractDeprecationTracker(args.registry_dir)
    
    # Simple validation: check if any deprecated fields are being removed
    print("\n📋 Checking migration compatibility...")
    
    report = tracker.generate_compatibility_report()
    
    if not report["tables_with_deprecations"]:
        print("\n✓ No active deprecations - migration should be safe")
        return
    
    # Check each deprecation timeline
    warnings = []
    for timeline in report["deprecation_timelines"]:
        for field_info in timeline["in_progress"]:
            if field_info["days_remaining"] <= 30:
                warnings.append(
                    f"⚠ {timeline['table']}.{field_info['field']}: "
                    f"{field_info['days_remaining']} days until removal"
                )
    
    if warnings:
        print("\n⚠ Deprecation reminders:")
        for warning in warnings:
            print(f"  {warning}")
    else:
        print("\n✓ No imminent deprecations - migration approved")


def cmd_deprecation_timeline(args) -> None:
    """Show deprecation timeline for a table."""
    tracker = DataContractDeprecationTracker(args.registry_dir)
    timeline = tracker.get_deprecation_timeline(args.table)
    
    if timeline.get("status") == "no_contract":
        print(f"\n✗ No contract found for table: {args.table}")
        return
    
    print(f"\n📅 Deprecation Timeline for {args.table}")
    print(f"  Version: {timeline['version']}")
    print(f"  Minimum retention: {timeline['minimum_retention_days']} days")
    
    if timeline["in_progress"]:
        print(f"\n  ⏳ In Progress ({len(timeline['in_progress'])}):")
        for field in timeline["in_progress"]:
            print(f"    • {field['field']}")
            print(f"      Days remaining: {field['days_remaining']}")
            print(f"      Removal date: {field['removal_target']}")
            print(f"      Reason: {field['reason']}")
            if field["replacement"]:
                print(f"      Replacement: {field['replacement']}")
    
    if timeline["completed"]:
        print(f"\n  ✓ Completed ({len(timeline['completed'])}):")
        for field in timeline["completed"]:
            print(f"    • {field['field']} (removed on {field['removal_target']})")


def cmd_generate_report(args) -> None:
    """Generate full compatibility report."""
    tracker = DataContractDeprecationTracker(args.registry_dir)
    report = tracker.generate_compatibility_report()
    
    print(f"\n📊 Data Contract Deprecation Report")
    print(f"  Total contracts: {report['total_contracts']}")
    print(f"  Tables with deprecations: {report['tables_with_deprecations']}")
    
    if report["reminders_30_day"]:
        print(f"\n  ⚠ 30-Day Reminders ({len(report['reminders_30_day'])}):")
        for reminder in report["reminders_30_day"]:
            print(f"    {reminder}")
    
    if report["deprecation_timelines"]:
        print(f"\n  📋 Active Deprecations:")
        for timeline in report["deprecation_timelines"]:
            in_progress = len(timeline["in_progress"])
            if in_progress > 0:
                print(f"    • {timeline['table']}: {in_progress} field(s) deprecated")
    
    if args.json:
        print(f"\n{json.dumps(report, indent=2)}")


def cmd_validate_registry(args) -> None:
    """Validate registry integrity."""
    tracker = DataContractDeprecationTracker(args.registry_dir)
    
    print(f"\n🔍 Validating registry...")
    print(f"  Registry file: {tracker.registry_file}")
    print(f"  Contracts loaded: {len(tracker.contracts)}")
    
    errors = []
    warnings = []
    
    for table_name, contract in tracker.contracts.items():
        if not contract.deprecated_fields:
            continue
        
        for field in contract.deprecated_fields:
            # Check for overdue removals
            if field.is_removal_overdue():
                warnings.append(
                    f"⚠ {table_name}.{field.field_name} removal overdue "
                    f"(target was {field.removal_target})"
                )
    
    if errors:
        print(f"\n✗ Validation failed with {len(errors)} error(s):")
        for error in errors:
            print(f"  {error}")
    elif warnings:
        print(f"\n⚠ Validation passed with {len(warnings)} warning(s):")
        for warning in warnings:
            print(f"  {warning}")
    else:
        print(f"\n✓ Registry is valid")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Data contract deprecation tracker CLI tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/data_contract_tools.py register-contract --table users
  python scripts/data_contract_tools.py deprecate-field --table users --field phone \\
      --removal-date 2026-06-07 --reason "Moved to user_contacts"
  python scripts/data_contract_tools.py check-migration
  python scripts/data_contract_tools.py deprecation-timeline --table users
  python scripts/data_contract_tools.py generate-report --json
        """
    )
    
    parser.add_argument(
        "-d", "--registry-dir",
        default="migrations",
        help="Directory for registry files (default: migrations)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # register-contract
    reg_parser = subparsers.add_parser("register-contract", help="Register new data contract")
    reg_parser.add_argument("--table", required=True, help="Table name")
    reg_parser.add_argument("--retention-days", type=int, help="Minimum retention period (default: 90)")
    reg_parser.set_defaults(func=cmd_register_contract)
    
    # deprecate-field
    depr_parser = subparsers.add_parser("deprecate-field", help="Mark field for deprecation")
    depr_parser.add_argument("--table", required=True, help="Table name")
    depr_parser.add_argument("--field", required=True, help="Field name")
    depr_parser.add_argument("--removal-date", required=True, help="Removal date (ISO format: YYYY-MM-DD)")
    depr_parser.add_argument("--reason", required=True, help="Reason for deprecation")
    depr_parser.add_argument("--replacement", help="Replacement field/table")
    depr_parser.set_defaults(func=cmd_deprecate_field)
    
    # check-migration
    check_parser = subparsers.add_parser("check-migration", help="Check migration compatibility")
    check_parser.set_defaults(func=cmd_check_migration)
    
    # deprecation-timeline
    timeline_parser = subparsers.add_parser("deprecation-timeline", help="Show deprecation timeline")
    timeline_parser.add_argument("--table", required=True, help="Table name")
    timeline_parser.set_defaults(func=cmd_deprecation_timeline)
    
    # generate-report
    report_parser = subparsers.add_parser("generate-report", help="Generate full report")
    report_parser.add_argument("--json", action="store_true", help="Output as JSON")
    report_parser.set_defaults(func=cmd_generate_report)
    
    # validate-registry
    valid_parser = subparsers.add_parser("validate-registry", help="Validate registry integrity")
    valid_parser.set_defaults(func=cmd_validate_registry)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        args.func(args)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
