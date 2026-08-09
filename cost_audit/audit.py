"""Resource scanners.

Each `find_*` function takes a boto3 client (or clients) and returns a list
of plain-dict findings. Keeping the functions pure and client-injected
(rather than constructing their own boto3 sessions) is what makes them
cheap to unit test with moto - no real AWS credentials or network calls
required.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from botocore.exceptions import ClientError

from cost_audit import pricing

DEFAULT_REQUIRED_TAGS = ["Environment", "CostCenter", "Owner"]
DEFAULT_CPU_THRESHOLD_PERCENT = 10.0
DEFAULT_LOOKBACK_HOURS = 24


def _tags_to_dict(tag_list: list[dict[str, str]] | None) -> dict[str, str]:
    return {t["Key"]: t["Value"] for t in (tag_list or [])}


def find_idle_ec2(
    ec2_client,
    cloudwatch_client,
    cpu_threshold: float = DEFAULT_CPU_THRESHOLD_PERCENT,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
) -> list[dict[str, Any]]:
    """Flag running instances whose average CPU utilization is below threshold."""
    findings = []
    paginator = ec2_client.get_paginator("describe_instances")
    for page in paginator.paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    ):
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                instance_id = instance["InstanceId"]
                instance_type = instance["InstanceType"]

                end = datetime.now(timezone.utc)
                start = end - timedelta(hours=lookback_hours)
                stats = cloudwatch_client.get_metric_statistics(
                    Namespace="AWS/EC2",
                    MetricName="CPUUtilization",
                    Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                    StartTime=start,
                    EndTime=end,
                    Period=3600,
                    Statistics=["Average"],
                )
                datapoints = stats.get("Datapoints", [])
                avg_cpu = (
                    sum(d["Average"] for d in datapoints) / len(datapoints)
                    if datapoints
                    else 0.0
                )

                if avg_cpu >= cpu_threshold:
                    continue

                try:
                    current_cost = pricing.ec2_monthly_cost(instance_type)
                except KeyError:
                    continue

                recommended_type = pricing.recommended_instance_type(instance_type)
                if recommended_type:
                    recommended_cost = pricing.ec2_monthly_cost(recommended_type)
                    savings = round(current_cost - recommended_cost, 2)
                    recommendation = f"downsize to {recommended_type}"
                else:
                    recommended_cost = current_cost
                    savings = 0.0
                    recommendation = (
                        "already at smallest tracked size - consider stopping if unused"
                    )

                findings.append(
                    {
                        "resource_id": instance_id,
                        "instance_type": instance_type,
                        "avg_cpu_percent": round(avg_cpu, 1),
                        "monthly_cost": current_cost,
                        "recommendation": recommendation,
                        "recommended_monthly_cost": recommended_cost,
                        "potential_monthly_savings": savings,
                    }
                )
    return findings


def find_unattached_ebs(ec2_client) -> list[dict[str, Any]]:
    """Flag EBS volumes not attached to any instance - pure wasted spend."""
    findings = []
    paginator = ec2_client.get_paginator("describe_volumes")
    for page in paginator.paginate(
        Filters=[{"Name": "status", "Values": ["available"]}]
    ):
        for volume in page["Volumes"]:
            size_gb = volume["Size"]
            findings.append(
                {
                    "resource_id": volume["VolumeId"],
                    "size_gb": size_gb,
                    "monthly_cost": pricing.ebs_monthly_cost(size_gb),
                    "recommendation": "delete if no longer needed, or snapshot then delete",
                    "potential_monthly_savings": pricing.ebs_monthly_cost(size_gb),
                }
            )
    return findings


def find_unattached_eips(ec2_client) -> list[dict[str, Any]]:
    """Flag Elastic IPs not associated with a running instance."""
    findings = []
    response = ec2_client.describe_addresses()
    for address in response.get("Addresses", []):
        if address.get("AssociationId"):
            continue
        findings.append(
            {
                "resource_id": address.get("AllocationId", address.get("PublicIp")),
                "public_ip": address.get("PublicIp"),
                "monthly_cost": pricing.eip_monthly_cost(),
                "recommendation": "release the address if it is not going to be reused",
                "potential_monthly_savings": pricing.eip_monthly_cost(),
            }
        )
    return findings


def find_buckets_without_lifecycle(s3_client) -> list[dict[str, Any]]:
    """Flag S3 buckets with no lifecycle configuration.

    Storage costs without a lifecycle policy tend to grow monotonically -
    logs, build artifacts, and old backups accumulate at full Standard
    pricing forever instead of transitioning to cheaper tiers or expiring.
    """
    findings = []
    for bucket in s3_client.list_buckets().get("Buckets", []):
        name = bucket["Name"]
        try:
            s3_client.get_bucket_lifecycle_configuration(Bucket=name)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code != "NoSuchLifecycleConfiguration":
                raise
            findings.append(
                {
                    "resource_id": name,
                    "recommendation": (
                        "add a lifecycle rule: transition to Standard-IA after 30 days, "
                        "expire after a defined retention window"
                    ),
                }
            )
    return findings


def find_missing_required_tags(
    ec2_client, required_tags: list[str] | None = None
) -> list[dict[str, Any]]:
    """Flag EC2 instances missing tags used for cost allocation/chargeback."""
    required = required_tags or DEFAULT_REQUIRED_TAGS
    findings = []
    paginator = ec2_client.get_paginator("describe_instances")
    for page in paginator.paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["running", "stopped"]}]
    ):
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                present = _tags_to_dict(instance.get("Tags"))
                missing = [tag for tag in required if tag not in present]
                if missing:
                    findings.append(
                        {
                            "resource_id": instance["InstanceId"],
                            "missing_tags": missing,
                            "recommendation": f"tag with: {', '.join(missing)}",
                        }
                    )
    return findings


def run_audit(
    ec2_client,
    cloudwatch_client,
    s3_client,
    required_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Run every check and roll up the total identified monthly waste."""
    idle_ec2 = find_idle_ec2(ec2_client, cloudwatch_client)
    unattached_ebs = find_unattached_ebs(ec2_client)
    unattached_eips = find_unattached_eips(ec2_client)
    buckets_without_lifecycle = find_buckets_without_lifecycle(s3_client)
    missing_tags = find_missing_required_tags(ec2_client, required_tags)

    total_savings = round(
        sum(f["potential_monthly_savings"] for f in idle_ec2)
        + sum(f["potential_monthly_savings"] for f in unattached_ebs)
        + sum(f["potential_monthly_savings"] for f in unattached_eips),
        2,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "idle_ec2": idle_ec2,
        "unattached_ebs": unattached_ebs,
        "unattached_eips": unattached_eips,
        "buckets_without_lifecycle": buckets_without_lifecycle,
        "missing_tags": missing_tags,
        "total_potential_monthly_savings": total_savings,
        "total_potential_annual_savings": round(total_savings * 12, 2),
    }
