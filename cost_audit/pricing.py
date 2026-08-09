"""On-demand pricing lookups.

Real FinOps tooling has to balance two constraints: the AWS Price List API
is authoritative but slow (multi-second calls per SKU, awkward filter
syntax) and rate-limited, while an audit needs to price dozens of resources
in a few seconds. This module keeps a small, explicitly-dated snapshot of
us-east-1 on-demand rates as the fast path, and exposes `refresh_from_api`
so the snapshot can be regenerated from the live Pricing API when accuracy
matters more than speed (e.g. a scheduled nightly job).

All rates are USD, us-east-1, on-demand, captured 2026-08-09.
"""

from __future__ import annotations

HOURS_PER_MONTH = 730  # standard AWS billing convention

EC2_HOURLY_RATES = {
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
}

# Right-size one instance family tier down when average utilization is low.
DOWNSIZE_MAP = {
    "t3.xlarge": "t3.large",
    "t3.large": "t3.medium",
    "t3.medium": "t3.small",
    "t3.small": "t3.micro",
}

EBS_GP3_MONTHLY_PER_GB = 0.08
EIP_IDLE_HOURLY_RATE = 0.005  # AWS charges for EIPs not associated with a running instance
S3_STANDARD_MONTHLY_PER_GB = 0.023
S3_STANDARD_IA_MONTHLY_PER_GB = 0.0125


def ec2_monthly_cost(instance_type: str) -> float:
    rate = EC2_HOURLY_RATES.get(instance_type)
    if rate is None:
        raise KeyError(f"No pricing snapshot for instance type {instance_type!r}")
    return round(rate * HOURS_PER_MONTH, 2)


def ebs_monthly_cost(size_gb: int) -> float:
    return round(size_gb * EBS_GP3_MONTHLY_PER_GB, 2)


def eip_monthly_cost() -> float:
    return round(EIP_IDLE_HOURLY_RATE * HOURS_PER_MONTH, 2)


def recommended_instance_type(instance_type: str) -> str | None:
    """Return one tier down, or None if already at the smallest tracked size."""
    return DOWNSIZE_MAP.get(instance_type)


def refresh_from_api(region: str = "us-east-1") -> dict:
    """Pull live on-demand EC2 rates from the AWS Price List API.

    Not called during a normal audit run (the static snapshot above is the
    fast path) - this is here so the snapshot can be regenerated on a
    schedule. Requires `pricing:GetProducts` and only works against the
    `us-east-1` Pricing API endpoint regardless of the region being priced.
    """
    import json

    import boto3

    client = boto3.client("pricing", region_name="us-east-1")
    region_names = {
        "us-east-1": "US East (N. Virginia)",
    }
    rates: dict[str, float] = {}
    for instance_type in EC2_HOURLY_RATES:
        response = client.get_products(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": region_names.get(region, region)},
                {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
            ],
            MaxResults=1,
        )
        for price_item in response.get("PriceList", []):
            product = json.loads(price_item)
            terms = product.get("terms", {}).get("OnDemand", {})
            for term in terms.values():
                for dimension in term.get("priceDimensions", {}).values():
                    rates[instance_type] = float(dimension["pricePerUnit"]["USD"])
    return rates
