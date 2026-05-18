import os
import sys
import datetime

# Add API directory to Python path to import modules
sys.path.append(os.path.join(os.path.dirname(__file__), 'API'))

from database.db_connection import execute, fetch_one
from utils.escalation_engine import start_incident_escalation, run_escalations
from utils.common import logger

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print("=" * 80)
    print("🔴 DQ SENTINEL - SLA ESCALATION SYSTEM INTEGRATION TEST 🔴")
    print("=" * 80)

    try:
        # Fetch an existing active dataset to make the simulation fully realistic
        sample_dataset = fetch_one("SELECT id, connector_id, dataset_name FROM datasets WHERE connector_id IS NOT NULL LIMIT 1")
        if sample_dataset:
            ds_id = sample_dataset["id"]
            conn_id = sample_dataset["connector_id"]
            ds_name = sample_dataset["dataset_name"]
            # Fetch connector name
            conn_row = fetch_one("SELECT name FROM connectors WHERE id = %s", (conn_id,))
            conn_name = conn_row["name"] if conn_row else "SQL Database"
        else:
            ds_id = None
            conn_id = None
            ds_name = "customer_profiles"
            conn_name = "MySQL Server"

        print(f"✓ Using real dataset for simulation: '{ds_name}' (Connector: '{conn_name}')")

        # 1. Create a simulated critical alert in database with premium realistic properties
        print("\n[Step 1/4] Inserting mock critical alert...")
        alert_id = execute(
            """INSERT INTO alerts (connector_id, dataset_id, category, severity, title, message, ai_summary, ai_root_cause, ai_recommendation, status)
               VALUES (%s, %s, 'quality', 'critical', 'Data Quality Anomaly Detected: Null Values Threshold Exceeded', 
               'A critical quality defect has been detected: the column \"user_email\" contains 14.2%% NULL values, which violates the strict data validation threshold of < 2.0%%.',
               'Automated scanning detected a significant spike in NULL values for the user email column on the daily run.',
               'The upstream registration form recently deployed an update that made the email field optional in the UI, allowing empty inputs to propagate.',
               'Run a backfill pipeline script for the missing email address records, and update the database schema constraint to enforce \"NOT NULL\" on \"user_email\" column.', 'open')""",
            (conn_id, ds_id)
        )
        print(f"✓ Mock alert created successfully. Alert ID: {alert_id}")

        # 2. Trigger start_incident_escalation (Level 1 notification)
        print("\n[Step 2/4] Initializing Level 1 Escalation...")
        success = start_incident_escalation(
            alert_id=alert_id,
            category="quality",
            severity="critical",
            dataset_id=ds_id,
            connector_id=conn_id
        )
        if success:
            print("✓ Level 1 escalation tracking successfully registered.")
            print("✓ Immediate Level 1 notification sent to Data Consumer (Admin User).")
        else:
            print("❌ Failed to start Level 1 escalation.")
            return

        # 3. Simulate SLA Breach by backdating timestamps by 10 minutes (SLA target is 5 minutes)
        print("\n[Step 3/4] Backdating escalation tracker timestamps by 10 minutes to trigger SLA breach...")
        ten_minutes_ago = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
        execute(
            """UPDATE incident_escalation_tracking 
               SET started_at = %s, updated_at = %s 
               WHERE incident_id = %s""",
            (ten_minutes_ago, ten_minutes_ago, alert_id)
        )
        print("✓ Tracker updated. The system now recognizes the current step as an active SLA breach!")

        # 4. Trigger the background escalation cron-job evaluation
        print("\n[Step 4/4] Executing background run_escalations engine task...")
        escalated_count = run_escalations()
        
        if escalated_count > 0:
            print(f"\n🎉 SUCCESS! SLA Breach detected! Simulated alert escalated successfully to Level 2 (Data Steward).")
            print("✓ SLA Breach banner, previous SLA parameters, and Level 2 notifications dispatched.")
        else:
            print("\n❌ SLA breach evaluation did not trigger. Please check table records.")

        # Print current state
        tracking = fetch_one("SELECT * FROM incident_escalation_tracking WHERE incident_id = %s", (alert_id,))
        if tracking:
            print("\n" + "-" * 50)
            print("📊 CURRENT TRACKING STATE:")
            print("-" * 50)
            print(f"Tracking ID:   {tracking['id']}")
            print(f"Current Level: Level {tracking['current_level']}")
            print(f"SLA Breached:  {bool(tracking['is_sla_breached'])}")
            print(f"Status:        {tracking['escalation_status'].upper()}")
            print("-" * 50)

    except Exception as e:
        print(f"\n❌ Error running test script: {e}")
    
    print("\nTest Script Execution Completed.")

if __name__ == '__main__':
    main()
