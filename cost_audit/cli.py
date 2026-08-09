"""Command-line entrypoint: python -m cost_audit --region us-east-1 --output report.md"""

from __future__ import annotations

import argparse
import sys

import boto3

from cost_audit import audit, report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cost_audit",
        description="Scan an AWS account for common sources of avoidable spend.",
    )
    parser.add_argument("--region", default="us-east-1", help="AWS region to scan")
    parser.add_argument("--profile", default=None, help="AWS CLI profile to use")
    parser.add_argument(
        "--output", default=None, help="Write the Markdown report to this file instead of stdout"
    )
    parser.add_argument(
        "--title", default="AWS Cost Audit Report", help="Report title"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    ec2 = session.client("ec2")
    cloudwatch = session.client("cloudwatch")
    s3 = session.client("s3")

    findings = audit.run_audit(ec2, cloudwatch, s3)
    markdown = report.render_markdown(findings, title=args.title)

    if args.output:
        with open(args.output, "w") as f:
            f.write(markdown)
        print(f"Report written to {args.output}", file=sys.stderr)
        print(
            f"Total identified waste: {findings['total_potential_monthly_savings']}/month",
            file=sys.stderr,
        )
    else:
        print(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
