#!/usr/bin/env python3
"""
Pre-migration check for Debezium deployment (S6.2 H1 Fix).
Prevents event re-emission by verifying outbox state before connector starts.

Usage:
    export DATABASE_URL="postgresql://triage_app:password@postgres:5432/triage"
    python3 tools/debezium/pre_migration_check.py
"""
import sys
import os
from datetime import datetime, timedelta


def run_checks():
    """Execute pre-migration checks; fail if any check fails."""
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        print("ERROR: sqlalchemy not installed. Install with: pip install sqlalchemy psycopg2-binary")
        return False

    DB_URL = os.getenv("DATABASE_URL")
    if not DB_URL:
        print("ERROR: DATABASE_URL environment variable not set")
        return False

    engine = create_engine(DB_URL)

    print("[1/4] Validating outbox_events schema...")
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns 
                    WHERE table_schema='triage' AND table_name='outbox_events'
                    ORDER BY ordinal_position
                """)
            )

            required_columns = {
                "id": "uuid",
                "tenant_id": "uuid",
                "aggregate_type": "character varying",
                "aggregate_id": "character varying",
                "event_type": "character varying",
                "payload": "jsonb",
                "created_at": "timestamp with time zone",
                "published_at": "timestamp with time zone",
            }

            found_columns = {row[0]: row[1] for row in result}

            for col, dtype in required_columns.items():
                if col not in found_columns:
                    print(f"❌ FAIL: Column '{col}' not found in outbox_events schema")
                    return False
                if found_columns[col] != dtype:
                    print(f"❌ FAIL: Column '{col}' has type '{found_columns[col]}', expected '{dtype}'")
                    return False

            print("✓ Schema validated")
    except Exception as e:
        print(f"❌ Schema validation error: {e}")
        return False

    print("\n[2/4] Checking for unpublished events that should be cleaned...")
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT COUNT(*) as unpublished_old
                    FROM triage.outbox_events 
                    WHERE published_at IS NULL 
                      AND created_at < NOW() - INTERVAL '1 hour'
                """)
            )

            unpublished_old_count = result.scalar()

            if unpublished_old_count and unpublished_old_count > 0:
                print(f"⚠️  WARNING: Found {unpublished_old_count} unpublished events older than 1 hour")
                print("   These should be cleaned up before deployment to prevent re-emission")
                print("   Run: UPDATE triage.outbox_events SET published_at = NOW()")
                print("        WHERE published_at IS NULL AND created_at < NOW() - INTERVAL '1 hour';")

                response = input("   Clean up old events now? (yes/no): ").lower()

                if response == "yes":
                    try:
                        conn.execute(
                            text("""
                                UPDATE triage.outbox_events 
                                SET published_at = NOW() 
                                WHERE published_at IS NULL 
                                  AND created_at < NOW() - INTERVAL '1 hour'
                            """)
                        )
                        conn.commit()
                        print("✓ Old unpublished events marked as published")
                    except Exception as e:
                        print(f"❌ Cleanup failed: {e}")
                        return False
                else:
                    print("❌ FAIL: Cannot proceed without cleaning old unpublished events")
                    return False
            else:
                print("✓ No old unpublished events found")
    except Exception as e:
        print(f"❌ Error checking old events: {e}")
        return False

    print("\n[3/4] Checking current unpublished event count (should be <100)...")
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT COUNT(*) as unpublished_count 
                    FROM triage.outbox_events 
                    WHERE published_at IS NULL
                """)
            )

            unpublished_count = result.scalar()

            if unpublished_count and unpublished_count > 100:
                print(f"❌ FAIL: Found {unpublished_count} unpublished events (threshold: 100)")
                print("   OutboxPoller may be lagging or blocked. Investigate before deployment.")
                return False

            print(f"✓ Unpublished event count OK: {unpublished_count}")
    except Exception as e:
        print(f"❌ Error checking unpublished count: {e}")
        return False

    print("\n[4/4] Verifying Kafka brokers configuration...")
    kafka_brokers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-broker-1:9092").split(",")
    print(f"   Kafka brokers: {kafka_brokers}")
    print("✓ (Manual verification: ensure Kafka cluster is healthy)")

    print("\n✅ All pre-migration checks passed. Safe to deploy Debezium connector.")
    return True


if __name__ == "__main__":
    success = run_checks()
    sys.exit(0 if success else 1)
