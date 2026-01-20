output "s3_bucket_name" {
  description = "S3 Bucket 名稱"
  value       = aws_s3_bucket.cafe_photos.id
}

output "s3_bucket_region" {
  description = "S3 Bucket 區域"
  value       = aws_s3_bucket.cafe_photos.region
}

output "cloudfront_domain" {
  description = "CloudFront 網域名稱"
  value       = aws_cloudfront_distribution.cafe_photos.domain_name
}

output "cloudfront_url" {
  description = "CloudFront 完整 URL"
  value       = "https://${aws_cloudfront_distribution.cafe_photos.domain_name}"
}

output "aws_access_key_id" {
  description = "Django App AWS Access Key ID"
  value       = aws_iam_access_key.django_app.id
  sensitive   = true # 不會直接顯示
}

output "aws_secret_access_key" {
  description = "Django App AWS Secret Access Key"
  value       = aws_iam_access_key.django_app.secret
  sensitive   = true # 不會直接顯示
}

# 使用方式：
# terraform output cloudfront_domain
# terraform output -raw aws_access_key_id
