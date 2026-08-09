output "instance_id" {
  value = aws_instance.right_sized.id
}

output "bucket_name" {
  value = aws_s3_bucket.logs.bucket
}

output "budget_name" {
  value = aws_budgets_budget.monthly.name
}
