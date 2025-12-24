

variable "aws_region" {
  description = "AWS 區域"
  type        = string
  default     = "ap-northeast-1"
}

variable "project_name" {
  description = "專案名稱"
  type        = string
  default     = "find-coffee"
}

variable "environment" {
  description = "環境名稱"
  type        = string
  default     = "production"
}

variable "s3_bucket_name" {
  description = "S3 bucket 名稱（必須全球唯一）"
  type        = string
  # 實際值在 terraform.tfvars
}
