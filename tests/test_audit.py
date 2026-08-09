import boto3
from moto import mock_aws

from cost_audit import audit, pricing


@mock_aws
def test_find_idle_ec2_flags_low_cpu_instance():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")

    ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        InstanceType="t3.large",
    )

    findings = audit.find_idle_ec2(ec2, cloudwatch)

    assert len(findings) == 1
    finding = findings[0]
    assert finding["instance_type"] == "t3.large"
    assert finding["recommendation"] == "downsize to t3.medium"
    assert finding["potential_monthly_savings"] == round(
        pricing.ec2_monthly_cost("t3.large") - pricing.ec2_monthly_cost("t3.medium"), 2
    )


@mock_aws
def test_find_idle_ec2_ignores_stopped_instances():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")

    run = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t3.large")
    instance_id = run["Instances"][0]["InstanceId"]
    ec2.stop_instances(InstanceIds=[instance_id])

    findings = audit.find_idle_ec2(ec2, cloudwatch)

    assert findings == []


@mock_aws
def test_find_unattached_ebs_flags_available_volumes():
    ec2 = boto3.client("ec2", region_name="us-east-1")

    ec2.create_volume(Size=50, AvailabilityZone="us-east-1a")

    findings = audit.find_unattached_ebs(ec2)

    assert len(findings) == 1
    assert findings[0]["size_gb"] == 50
    assert findings[0]["monthly_cost"] == pricing.ebs_monthly_cost(50)


@mock_aws
def test_find_unattached_ebs_ignores_attached_volumes():
    ec2 = boto3.client("ec2", region_name="us-east-1")

    run = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t3.micro")
    instance_id = run["Instances"][0]["InstanceId"]
    volume = ec2.create_volume(Size=20, AvailabilityZone="us-east-1a")
    ec2.attach_volume(
        VolumeId=volume["VolumeId"], InstanceId=instance_id, Device="/dev/sdf"
    )

    findings = audit.find_unattached_ebs(ec2)

    assert findings == []


@mock_aws
def test_find_unattached_eips_flags_unassociated_address():
    ec2 = boto3.client("ec2", region_name="us-east-1")

    ec2.allocate_address(Domain="vpc")

    findings = audit.find_unattached_eips(ec2)

    assert len(findings) == 1
    assert findings[0]["monthly_cost"] == pricing.eip_monthly_cost()


@mock_aws
def test_find_buckets_without_lifecycle():
    s3 = boto3.client("s3", region_name="us-east-1")

    s3.create_bucket(Bucket="no-lifecycle-bucket")
    s3.create_bucket(Bucket="has-lifecycle-bucket")
    s3.put_bucket_lifecycle_configuration(
        Bucket="has-lifecycle-bucket",
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "expire-old-objects",
                    "Status": "Enabled",
                    "Filter": {},
                    "Expiration": {"Days": 90},
                }
            ]
        },
    )

    findings = audit.find_buckets_without_lifecycle(s3)

    flagged_names = {f["resource_id"] for f in findings}
    assert "no-lifecycle-bucket" in flagged_names
    assert "has-lifecycle-bucket" not in flagged_names


@mock_aws
def test_find_missing_required_tags():
    ec2 = boto3.client("ec2", region_name="us-east-1")

    ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        InstanceType="t3.micro",
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Environment", "Value": "prod"}],
            }
        ],
    )
    ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        InstanceType="t3.micro",
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Environment", "Value": "prod"},
                    {"Key": "CostCenter", "Value": "eng"},
                    {"Key": "Owner", "Value": "platform-team"},
                ],
            }
        ],
    )

    findings = audit.find_missing_required_tags(ec2)

    assert len(findings) == 1
    assert set(findings[0]["missing_tags"]) == {"CostCenter", "Owner"}


@mock_aws
def test_run_audit_totals_match_component_savings():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")
    s3 = boto3.client("s3", region_name="us-east-1")

    ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t3.large")
    ec2.create_volume(Size=100, AvailabilityZone="us-east-1a")
    ec2.allocate_address(Domain="vpc")
    s3.create_bucket(Bucket="some-bucket")

    findings = audit.run_audit(ec2, cloudwatch, s3)

    expected_total = round(
        sum(f["potential_monthly_savings"] for f in findings["idle_ec2"])
        + sum(f["potential_monthly_savings"] for f in findings["unattached_ebs"])
        + sum(f["potential_monthly_savings"] for f in findings["unattached_eips"]),
        2,
    )
    assert findings["total_potential_monthly_savings"] == expected_total
    assert findings["total_potential_annual_savings"] == round(expected_total * 12, 2)
    assert len(findings["idle_ec2"]) == 1
    assert len(findings["unattached_ebs"]) == 1
    assert len(findings["unattached_eips"]) == 1
    assert len(findings["buckets_without_lifecycle"]) == 1
