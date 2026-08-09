"""AWS cost audit toolkit.

A small, testable library + CLI for flagging common sources of AWS waste:
idle/oversized EC2 instances, unattached EBS volumes, unattached Elastic IPs,
S3 buckets with no lifecycle policy, and resources missing required cost
allocation tags.
"""

__version__ = "0.1.0"
