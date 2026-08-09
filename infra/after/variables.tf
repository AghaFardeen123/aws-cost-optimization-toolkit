variable "aws_region" {
  type        = string
  description = "AWS region to deploy the after-scenario into."
  default     = "us-east-1"
}

variable "admin_cidr" {
  type        = string
  description = "CIDR allowed to SSH into the demo instance."
}

variable "environment" {
  type        = string
  description = "Environment tag applied to every resource."
  default     = "demo"
}

variable "cost_center" {
  type        = string
  description = "Cost center tag applied to every resource."
  default     = "engineering"
}

variable "owner" {
  type        = string
  description = "Owner tag applied to every resource."
  default     = "platform-team"
}

variable "monthly_budget_limit_usd" {
  type        = string
  description = "Monthly budget ceiling in USD."
  default     = "50"
}

variable "budget_notification_email" {
  type        = string
  description = "Email address to notify on budget threshold and cost anomalies."
}
