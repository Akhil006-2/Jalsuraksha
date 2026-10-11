"""
JalSuraksha — SageMaker built-in XGBoost training runner
Region: eu-north-1
Input CSVs: label-first, headerless SageMaker XGBoost format.

Run from the project's activated virtual environment:
    python run_sagemaker_training.py

The script asks for explicit confirmation before creating a billable training job.
It writes local status checkpoints to:
    runs/sagemaker_susceptibility/<job-name>/checkpoint.json
and logs to:
    runs/sagemaker_susceptibility/<job-name>/training.log

To resume monitoring an existing job:
    python run_sagemaker_training.py --monitor <training-job-name>
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

REGION = "eu-north-1"
ACCOUNT_ID = "302761015574"
ROLE_ARN = (
    "arn:aws:iam::302761015574:role/"
    "JalsurakshaSageMakerExecutionRole"
)
BUCKET = "jalsuraksha-chennai-2026-ap-south-1"
INPUT_PREFIX = "training/susceptibility_v1"
OUTPUT_PREFIX = "models/susceptibility_v1"
IMAGE_URI = (
    "662702820516.dkr.ecr.eu-north-1.amazonaws.com/"
    "sagemaker-xgboost:3.0-5"
)
INSTANCE_TYPE = "ml.m5.large"
VOLUME_GB = 5
MAX_RUNTIME_SECONDS = 3600
POLL_SECONDS = 30

ROOT = Path.cwd()
RUNS_DIR = ROOT / "runs" / "sagemaker_susceptibility"

TERMINAL_STATES = {"Completed", "Failed", "Stopped"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def make_job_name():
    return "jalsuraksha-xgb-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    temp.replace(path)


def configure_logging(log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )


def check_inputs(s3):
    for key in (f"{INPUT_PREFIX}/train.csv", f"{INPUT_PREFIX}/validation.csv"):
        response = s3.head_object(Bucket=BUCKET, Key=key)
        size = response["ContentLength"]
        if size <= 0:
            raise RuntimeError(f"S3 input is empty: s3://{BUCKET}/{key}")
        logging.info("Input verified: s3://%s/%s (%s bytes)", BUCKET, key, size)


def create_job(sm, job_name):
    sm.create_training_job(
        TrainingJobName=job_name,
        RoleArn=ROLE_ARN,
        AlgorithmSpecification={
            "TrainingImage": IMAGE_URI,
            "TrainingInputMode": "File",
        },
        HyperParameters={
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "num_round": "100",
            "max_depth": "4",
            "eta": "0.1",
            "subsample": "0.8",
            "colsample_bytree": "0.8",
            "min_child_weight": "5",
        },
        InputDataConfig=[
            {
                "ChannelName": "train",
                "DataSource": {
                    "S3DataSource": {
                        "S3DataType": "S3Prefix",
                        "S3Uri": f"s3://{BUCKET}/{INPUT_PREFIX}/train.csv",
                        "S3DataDistributionType": "FullyReplicated",
                    }
                },
                "ContentType": "text/csv",
                "CompressionType": "None",
                "RecordWrapperType": "None",
            },
            {
                "ChannelName": "validation",
                "DataSource": {
                    "S3DataSource": {
                        "S3DataType": "S3Prefix",
                        "S3Uri": f"s3://{BUCKET}/{INPUT_PREFIX}/validation.csv",
                        "S3DataDistributionType": "FullyReplicated",
                    }
                },
                "ContentType": "text/csv",
                "CompressionType": "None",
                "RecordWrapperType": "None",
            },
        ],
        OutputDataConfig={
            "S3OutputPath": f"s3://{BUCKET}/{OUTPUT_PREFIX}/"
        },
        ResourceConfig={
            "InstanceType": INSTANCE_TYPE,
            "InstanceCount": 1,
            "VolumeSizeInGB": VOLUME_GB,
        },
        StoppingCondition={
            "MaxRuntimeInSeconds": MAX_RUNTIME_SECONDS
        },
        EnableNetworkIsolation=False,
        Tags=[
            {"Key": "Project", "Value": "JalSuraksha"},
            {"Key": "Purpose", "Value": "PreliminaryFloodSusceptibility"},
        ],
    )


def fetch_recent_logs(logs_client, job_name, seen_events):
    """Print new CloudWatch log events when the log stream is available."""
    group = "/aws/sagemaker/TrainingJobs"
    try:
        streams = logs_client.describe_log_streams(
            logGroupName=group,
            logStreamNamePrefix=job_name,
            orderBy="LastEventTime",
            descending=True,
            limit=10,
        ).get("logStreams", [])
        for stream in streams:
            stream_name = stream["logStreamName"]
            token = seen_events.get(stream_name)
            kwargs = {
                "logGroupName": group,
                "logStreamName": stream_name,
                "startFromHead": True,
            }
            if token:
                kwargs["nextToken"] = token
            response = logs_client.get_log_events(**kwargs)
            for event in response.get("events", []):
                message = event.get("message", "").rstrip()
                if message:
                    logging.info("[SageMaker] %s", message)
            if response.get("nextForwardToken"):
                seen_events[stream_name] = response["nextForwardToken"]
    except logs_client.exceptions.ResourceNotFoundException:
        # Log group/stream may not exist immediately after job creation.
        return
    except ClientError as exc:
        logging.debug("CloudWatch log read not available yet: %s", exc)


def monitor_job(sm, logs_client, job_name, checkpoint_path, log_path):
    configure_logging(log_path)
    seen_events = {}
    last_status = None
    logging.info("Monitoring training job: %s", job_name)
    logging.info("Local checkpoint: %s", checkpoint_path)

    try:
        while True:
            description = sm.describe_training_job(TrainingJobName=job_name)
            status = description["TrainingJobStatus"]
            secondary = description.get("SecondaryStatus", "Unknown")
            failure_reason = description.get("FailureReason")
            metrics = description.get("FinalMetricDataList", [])
            output_uri = description.get("ModelArtifacts", {}).get("S3ModelArtifacts")

            snapshot = {
                "project": "JalSuraksha",
                "training_job_name": job_name,
                "region": REGION,
                "checked_at_utc": utc_now(),
                "training_job_status": status,
                "secondary_status": secondary,
                "failure_reason": failure_reason,
                "training_start_time": description.get("TrainingStartTime"),
                "training_end_time": description.get("TrainingEndTime"),
                "billable_seconds": description.get("BillableTimeInSeconds"),
                "instance_type": description.get("ResourceConfig", {}).get("InstanceType"),
                "model_artifact_s3_uri": output_uri,
                "final_metrics": metrics,
            }
            write_json(checkpoint_path, snapshot)

            if status != last_status:
                logging.info("Status: %s | Secondary status: %s", status, secondary)
                last_status = status
            else:
                logging.info("Still %s | %s", status, secondary)

            fetch_recent_logs(logs_client, job_name, seen_events)

            if status in TERMINAL_STATES:
                if status == "Completed":
                    logging.info("TRAINING COMPLETED.")
                    logging.info("Model artifact: %s", output_uri)
                    logging.info("Final metrics: %s", json.dumps(metrics, default=str))
                elif status == "Failed":
                    logging.error("TRAINING FAILED: %s", failure_reason)
                else:
                    logging.warning("Training job stopped.")
                logging.info("Final checkpoint saved: %s", checkpoint_path)
                return 0 if status == "Completed" else 2

            time.sleep(POLL_SECONDS)

    except KeyboardInterrupt:
        logging.warning(
            "Monitoring interrupted. The AWS training job may still be running; "
            "it was NOT automatically stopped."
        )
        logging.warning("Resume with: python run_sagemaker_training.py --monitor %s", job_name)
        return 130
    except (BotoCoreError, ClientError) as exc:
        logging.exception("AWS error while monitoring: %s", exc)
        logging.error(
            "If the job was created, resume monitoring with: "
            "python run_sagemaker_training.py --monitor %s",
            job_name,
        )
        return 3


def main():
    parser = argparse.ArgumentParser(description="Train JalSuraksha XGBoost model on SageMaker.")
    parser.add_argument(
        "--monitor",
        metavar="TRAINING_JOB_NAME",
        help="Monitor an already-created SageMaker training job instead of creating one.",
    )
    args = parser.parse_args()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    session = boto3.Session(region_name=REGION)
    sts = session.client("sts")
    identity = sts.get_caller_identity()
    if identity["Account"] != ACCOUNT_ID:
        raise RuntimeError(
            f"Unexpected AWS account {identity['Account']}; expected {ACCOUNT_ID}. "
            "Stopping to avoid launching resources in the wrong account."
        )

    sm = session.client("sagemaker")
    s3 = session.client("s3")
    logs_client = session.client("logs")

    if args.monitor:
        job_name = args.monitor
        job_dir = RUNS_DIR / job_name
        return monitor_job(
            sm, logs_client, job_name,
            job_dir / "checkpoint.json",
            job_dir / "training.log",
        )

    job_name = make_job_name()
    job_dir = RUNS_DIR / job_name
    checkpoint_path = job_dir / "checkpoint.json"
    log_path = job_dir / "training.log"
    configure_logging(log_path)

    logging.info("AWS identity: %s", identity["Arn"])
    logging.info("Region: %s", REGION)
    logging.info("Training image: %s", IMAGE_URI)
    logging.info("Instance: 1 x %s, EBS volume %s GiB", INSTANCE_TYPE, VOLUME_GB)
    logging.info("Training input: s3://%s/%s/train.csv", BUCKET, INPUT_PREFIX)
    logging.info("Validation input: s3://%s/%s/validation.csv", BUCKET, INPUT_PREFIX)
    logging.info("Output prefix: s3://%s/%s/", BUCKET, OUTPUT_PREFIX)
    logging.info(
        "Scientific limitation: labels are 2015 mapped inundation vs background "
        "pseudoabsence. This is preliminary susceptibility, not validated live forecasting."
    )

    try:
        check_inputs(s3)
        # Check the role exists before requesting the job.
        iam = session.client("iam")
        role = iam.get_role(RoleName="JalsurakshaSageMakerExecutionRole")["Role"]
        if role["Arn"] != ROLE_ARN:
            raise RuntimeError(f"Role ARN mismatch: {role['Arn']}")

        # Initial checkpoint exists even if creation fails.
        write_json(checkpoint_path, {
            "project": "JalSuraksha",
            "training_job_name": job_name,
            "region": REGION,
            "created_locally_at_utc": utc_now(),
            "training_job_status": "NotStarted",
            "model_output_prefix": f"s3://{BUCKET}/{OUTPUT_PREFIX}/",
        })

        print("\nREADY TO LAUNCH SAGEMAKER TRAINING")
        print(f"Job name:       {job_name}")
        print(f"Region:         {REGION}")
        print(f"Instance:       1 x {INSTANCE_TYPE}")
        print(f"Max runtime:    {MAX_RUNTIME_SECONDS // 60} minutes")
        print(f"Model outputs:  s3://{BUCKET}/{OUTPUT_PREFIX}/")
        print(f"Local progress: {checkpoint_path}")
        print("\nThis starts a billable SageMaker training job. Charges depend on actual runtime.")
        answer = input('Type LAUNCH to start training, or anything else to cancel: ').strip()
        if answer != "LAUNCH":
            logging.info("Cancelled. No SageMaker training job was launched.")
            return 0

        create_job(sm, job_name)
        write_json(checkpoint_path, {
            "project": "JalSuraksha",
            "training_job_name": job_name,
            "region": REGION,
            "created_at_utc": utc_now(),
            "training_job_status": "InProgress",
            "model_output_prefix": f"s3://{BUCKET}/{OUTPUT_PREFIX}/",
        })
        logging.info("Training job created successfully: %s", job_name)

    except KeyboardInterrupt:
        logging.warning("Interrupted before training-job creation completed.")
        return 130
    except (BotoCoreError, ClientError, RuntimeError) as exc:
        logging.exception("Preflight or training-job creation failed: %s", exc)
        write_json(checkpoint_path, {
            "project": "JalSuraksha",
            "training_job_name": job_name,
            "region": REGION,
            "checked_at_utc": utc_now(),
            "training_job_status": "CreationFailedOrCancelled",
            "error": str(exc),
        })
        return 2

    return monitor_job(sm, logs_client, job_name, checkpoint_path, log_path)


if __name__ == "__main__":
    sys.exit(main())
