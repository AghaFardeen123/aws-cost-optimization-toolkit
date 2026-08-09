output "instance_id" {
  value = aws_instance.oversized.id
}

output "orphaned_volume_id" {
  value = aws_ebs_volume.orphaned.id
}

output "unattached_eip" {
  value = aws_eip.unattached.public_ip
}

output "bucket_name" {
  value = aws_s3_bucket.logs.bucket
}
