# aws-cost-optimization-toolkit

A small FinOps toolkit: a Python audit CLI that scans an AWS account for
avoidable spend, and a paired Terraform "before / after" scenario that
proves the findings are real - deployed against live AWS, audited, fixed,
and re-audited.

## What it catches

| Check | Why it matters |
| --- | --- |
| Idle / oversized EC2 instances (low avg CPU) | The most common source of waste - paying for capacity nobody uses |
| Unattached EBS volumes | Billed at full price whether or not anything is reading from them |
| Unattached Elastic IPs | AWS charges for IPs that aren't associated with a running instance |
| S3 buckets with no lifecycle policy | Storage that grows forever instead of aging into cheaper tiers |
| Resources missing cost-allocation tags | Can't attribute or control spend you can't attribute to a team |

Each finding includes the estimated current monthly cost, a concrete
recommendation, and (where applicable) the projected monthly savings.

## How it's built

- `cost_audit/` - the scanner + pricing + report library, built so every
  AWS call goes through an injected boto3 client. That's what makes the
  test suite fast and hermetic: `tests/` uses [moto](https://github.com/getmoto/moto)
  to mock EC2, EBS, EIP, and S3 state and asserts on the exact findings,
  with no real AWS account required to run `pytest`.
- `cost_audit/pricing.py` - a dated on-demand pricing snapshot for the fast
  path, plus a `refresh_from_api` helper that pulls live rates from the AWS
  Price List API when accuracy matters more than speed.
- `infra/before/` - an intentionally under-governed stack: an oversized
  idle `t3.large`, an orphaned EBS volume, an unattached Elastic IP, an S3
  bucket with no lifecycle rule, and no cost-allocation tags.
- `infra/after/` - the remediated stack: a right-sized `t3.micro`, no
  orphaned resources, an S3 lifecycle rule, an AWS Budget with an 80%
  threshold alert, an AWS Cost Anomaly Detection monitor, and tags applied
  to every resource automatically via the provider's `default_tags`.
- `.github/workflows/ci.yml` - `flake8` + `pytest` on the Python package,
  `terraform fmt/validate` on both stacks, `tflint --recursive`, and `tfsec`
  (soft-fail, informational).

## Running it

```bash
pip install -r requirements.txt
python -m cost_audit --region us-east-1 --output report.md
```

Requires AWS credentials with read access to EC2, CloudWatch, and S3
(`ec2:Describe*`, `cloudwatch:GetMetricStatistics`, `s3:ListAllMyBuckets`,
`s3:GetLifecycleConfiguration`).

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

No AWS account needed - the test suite runs entirely against moto's
in-memory AWS mocks.

## Proof: before vs. after

`infra/before` and `infra/after` were both deployed to a real AWS account,
audited with this tool, then torn down. See [`reports/`](./reports) for the
actual generated output and the README section below for the summary.

<!-- SAVINGS_SUMMARY -->

## Why this setup

Most cost-optimization requests on Upwork aren't "build me a dashboard" -
they're "tell me what's wasting money and prove the fix works." This
project is built to be handed to a client's actual account: point the CLI
at it, get a findings report with real dollar figures in minutes, and reuse
the `infra/after` patterns (tagging via `default_tags`, S3 lifecycle rules,
budget alerts, anomaly detection) as a starting point for their real
environment.
