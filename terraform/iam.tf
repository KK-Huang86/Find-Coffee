# ============================================
# IAM User（給 Django 使用）
# ============================================

resource "aws_iam_user" "django_app" {
  name = "${var.project_name}-django-app"

  tags = {
    Name        = "Django App User"
    Application = "Django"
  }
}

# IAM Policy（限制只能操作照片 bucket）
resource "aws_iam_policy" "s3_upload" {
  name        = "${var.project_name}-s3-upload-policy"
  description = "Allow Django to upload photos to S3"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3PhotosBucketOperations"
        Effect = "Allow"
        Action = [
          "s3:PutObject",       # 上傳檔案
          "s3:PutObjectAcl",    # 設定檔案權限
          "s3:GetObject",       # 讀取檔案
          "s3:DeleteObject"     # 刪除檔案
        ]
        Resource = "${aws_s3_bucket.cafe_photos.arn}/*"
      },
      {
        Sid    = "AllowListBucket"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"       # 列出檔案
        ]
        Resource = aws_s3_bucket.cafe_photos.arn
      }
    ]
  })
}

# 綁定 Policy 到 User
resource "aws_iam_user_policy_attachment" "django_s3_upload" {
  user       = aws_iam_user.django_app.name
  policy_arn = aws_iam_policy.s3_upload.arn
}

# 建立 Access Key（給 Django 用）
resource "aws_iam_access_key" "django_app" {
  user = aws_iam_user.django_app.name
}
