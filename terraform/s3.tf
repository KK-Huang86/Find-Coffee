resource "aws_s3_bucket" "cafe_photos" {
  bucket = var.s3_bucket_name

  tags = {
    Name        = var.project_name
    Environment = "production"
    ManagedBy   = "Terraform"
  }
}

# 封鎖所有公開訪問（private）
resource "aws_s3_bucket_public_access_block" "cafe_photos" {
  bucket = aws_s3_bucket.cafe_photos.id

  block_public_acls       = true # 封鎖公開的 ACL
  block_public_policy     = true # 封鎖公開的 Bucket Policy
  ignore_public_acls      = true # 忽略所有公開的 ACL
  restrict_public_buckets = true # 限制公開的 bucket
}


# Cloudfront 設定

# 建立 CloudFront Distribution 和 OAC

# 1. 建立 Origin Access Control (OAC) -> 作為身分認證，得以通過 s3 bucket policy
resource "aws_cloudfront_origin_access_control" "cafe_photos" {
  name                              = "${var.s3_bucket_name}-oac"
  description                       = "OAC for ${var.s3_bucket_name}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# 2. 建立 CloudFront Distribution
resource "aws_cloudfront_distribution" "cafe_photos" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.project_name} Cafe Photos CDN"
  default_root_object = ""

  # 價格等級：使用北美、歐洲、亞洲的邊緣節點
  price_class = "PriceClass_200"

  # === 設定 Origin (來源) ===
  origin {
    # S3 的區域性網域名稱
    domain_name = aws_s3_bucket.cafe_photos.bucket_regional_domain_name

    # Origin ID（自訂的識別名稱）
    origin_id = "S3-${var.s3_bucket_name}"

    # 連接 OAC（CloudFront 用這個身份訪問 S3）
    origin_access_control_id = aws_cloudfront_origin_access_control.cafe_photos.id
  }

  # === 預設快取行為 ===
  default_cache_behavior {
    # 允許的 HTTP 方法
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${var.s3_bucket_name}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    # 強制使用 HTTPS
    viewer_protocol_policy = "redirect-to-https"

    # 快取時間設定
    min_ttl     = 0
    default_ttl = 3600  # 1 小時
    max_ttl     = 86400 # 24 小時

    # 啟用 Gzip 壓縮
    compress = true
  }

  # === 地理限制（這裡不限制） ===
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # === SSL/TLS 憑證設定 ===
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name        = "${var.project_name}-cdn"
    Environment = "production"
    ManagedBy   = "Terraform"
  }
}


# 設置 S3 bucket policy
# 不公開 Bucket Policy，允許 Cloudfront 的私人連線

resource "aws_s3_bucket_policy" "cafe_photos" {
  bucket = aws_s3_bucket.cafe_photos.id

  # 這個 policy 必須等 CloudFront 建立後才能套用
  depends_on = [
    aws_cloudfront_distribution.cafe_photos
  ]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"

        # 只允許 CloudFront 服務
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }

        # 只允許讀取
        Action = "s3:GetObject"

        # 套用到這個 bucket 的所有檔案 「/*」
        Resource = "${aws_s3_bucket.cafe_photos.arn}/*"

        # 認可的 CloudFront distribution
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.cafe_photos.arn
          }
        }
      }
    ]
  })
}
