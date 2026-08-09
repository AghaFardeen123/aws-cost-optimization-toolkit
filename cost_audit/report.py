"""Render an audit result dict into a Markdown report."""

from __future__ import annotations

from typing import Any


def _money(amount) -> str:
    return "$" + str(amount)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None found._\n"
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(findings: dict[str, Any], title: str = "AWS Cost Audit Report") -> str:
    sections = []

    sections.append(f"# {title}\n")
    sections.append(f"Generated: {findings['generated_at']}\n")
    sections.append(
        "**Total identified waste: " + _money(findings["total_potential_monthly_savings"]) + "/month "
        + "(" + _money(findings["total_potential_annual_savings"]) + "/year)**\n"
    )

    sections.append("## Idle / oversized EC2 instances\n")
    sections.append(
        _table(
            ["Instance", "Type", "Avg CPU %", "Monthly cost", "Recommendation", "Savings/mo"],
            [
                [
                    f["resource_id"],
                    f["instance_type"],
                    f["avg_cpu_percent"],
                    _money(f["monthly_cost"]),
                    f["recommendation"],
                    _money(f["potential_monthly_savings"]),
                ]
                for f in findings["idle_ec2"]
            ],
        )
    )

    sections.append("## Unattached EBS volumes\n")
    sections.append(
        _table(
            ["Volume", "Size (GB)", "Monthly cost", "Recommendation"],
            [
                [f["resource_id"], f["size_gb"], _money(f["monthly_cost"]), f["recommendation"]]
                for f in findings["unattached_ebs"]
            ],
        )
    )

    sections.append("## Unattached Elastic IPs\n")
    sections.append(
        _table(
            ["Allocation", "Public IP", "Monthly cost", "Recommendation"],
            [
                [f["resource_id"], f["public_ip"], _money(f["monthly_cost"]), f["recommendation"]]
                for f in findings["unattached_eips"]
            ],
        )
    )

    sections.append("## S3 buckets without a lifecycle policy\n")
    sections.append(
        _table(
            ["Bucket", "Recommendation"],
            [[f["resource_id"], f["recommendation"]] for f in findings["buckets_without_lifecycle"]],
        )
    )

    sections.append("## Resources missing required cost-allocation tags\n")
    sections.append(
        _table(
            ["Resource", "Missing tags"],
            [
                [f["resource_id"], ", ".join(f["missing_tags"])]
                for f in findings["missing_tags"]
            ],
        )
    )

    return "\n".join(sections)
