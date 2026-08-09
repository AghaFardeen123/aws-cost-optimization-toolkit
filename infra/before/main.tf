terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# Intentionally under-governed "before" stack used to demonstrate what the
# audit tool catches: an oversized/idle instance, an orphaned EBS volume, an
# unattached Elastic IP, an S3 bucket with no lifecycle policy, and missing
# cost-allocation tags. Do not copy this file as a starting point for a real
# environment.

provider "aws" {
  region = var.aws_region
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

resource "aws_security_group" "before" {
  name_prefix = "cost-demo-before-"
  description = "Demo security group for the cost-audit before scenario"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH from admin CIDR"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Intentionally not tagged with the required cost-allocation tags.
}

# Oversized for an idle demo workload - the audit tool should flag this and
# recommend downsizing.
resource "aws_instance" "oversized" {
  ami                     = data.aws_ami.amazon_linux.id
  instance_type           = "t3.large"
  subnet_id               = data.aws_subnets.default.ids[0]
  vpc_security_group_ids  = [aws_security_group.before.id]

  root_block_device {
    volume_size = 8
    volume_type = "gp3"
    encrypted   = true
  }

  # Intentionally missing Environment / CostCenter / Owner tags.
  tags = {
    Name = "cost-demo-before-oversized"
  }
}

# Orphaned volume - never attached to anything, pure wasted spend.
resource "aws_ebs_volume" "orphaned" {
  availability_zone = aws_instance.oversized.availability_zone
  size              = 20
  type              = "gp3"

  tags = {
    Name = "cost-demo-before-orphaned-volume"
  }
}

# Allocated but never associated - AWS bills idle Elastic IPs.
resource "aws_eip" "unattached" {
  domain = "vpc"

  tags = {
    Name = "cost-demo-before-unattached-eip"
  }
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# No lifecycle configuration - storage cost grows unbounded.
resource "aws_s3_bucket" "logs" {
  bucket = "cost-demo-before-logs-${random_id.bucket_suffix.hex}"

  tags = {
    Name = "cost-demo-before-logs"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
