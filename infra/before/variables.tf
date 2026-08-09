variable "aws_region" {
  type        = string
  description = "AWS region to deploy the before-scenario into."
  default     = "us-east-1"
}

variable "admin_cidr" {
  type        = string
  description = "CIDR allowed to SSH into the demo instance."
}
