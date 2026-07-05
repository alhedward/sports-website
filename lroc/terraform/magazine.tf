# LROC Magazine Production Foundation
# Kept separate from main.tf so this module can be ported to other club sites later.

data "archive_file" "magazine_api_lambda" {
  type        = "zip"
  source_file = "${path.module}/../lambda/magazine_api.py"
  output_path = "${path.module}/build/magazine_api.zip"
}

resource "aws_dynamodb_table" "magazine" {
  name         = "${local.name_prefix}-magazine-production"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "gsi1pk"
    type = "S"
  }

  attribute {
    name = "gsi1sk"
    type = "S"
  }

  attribute {
    name = "gsi2pk"
    type = "S"
  }

  attribute {
    name = "gsi2sk"
    type = "S"
  }

  global_secondary_index {
    name            = "gsi1"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "gsi2"
    hash_key        = "gsi2pk"
    range_key       = "gsi2sk"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Component = "magazine-production"
  }
}

resource "aws_iam_role" "magazine_api" {
  name = "${local.name_prefix}-magazine-api-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Component = "magazine-production"
  }
}

resource "aws_iam_role_policy_attachment" "magazine_api_basic" {
  role       = aws_iam_role.magazine_api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "magazine_api" {
  name = "${local.name_prefix}-magazine-api-inline"
  role = aws_iam_role.magazine_api.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ],
        Resource = [
          aws_dynamodb_table.magazine.arn,
          "${aws_dynamodb_table.magazine.arn}/index/*",
          aws_dynamodb_table.member_metadata.arn,
          aws_dynamodb_table.mail_state.arn,
          "${aws_dynamodb_table.mail_state.arn}/index/*"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ],
        Resource = [
          "${aws_s3_bucket.member_files.arn}/magazine/*",
          "${aws_s3_bucket.member_files.arn}/webmail/submissions/*"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:ListBucket"
        ],
        Resource = aws_s3_bucket.member_files.arn,
        Condition = {
          StringLike = {
            "s3:prefix" = ["magazine/*", "webmail/submissions/*"]
          }
        }
      }
    ]
  })
}

resource "aws_lambda_function" "magazine_api" {
  function_name    = "${local.name_prefix}-magazine-api"
  role             = aws_iam_role.magazine_api.arn
  handler          = "magazine_api.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.magazine_api_lambda.output_path
  source_code_hash = data.archive_file.magazine_api_lambda.output_base64sha256
  timeout          = 60
  memory_size      = 512

  environment {
    variables = {
      MAGAZINE_TABLE                 = aws_dynamodb_table.magazine.name
      EMAIL_STATE_TABLE              = aws_dynamodb_table.mail_state.name
      MEMBER_METADATA_TABLE          = aws_dynamodb_table.member_metadata.name
      MAGAZINE_ASSETS_BUCKET         = aws_s3_bucket.member_files.bucket
      MAGAZINE_ASSETS_PREFIX         = "magazine/"
      MAGAZINE_UPLOAD_EXPIRY_SECONDS = "3600"
      # Direct browser-to-S3 uploads are used, so this does not hit API Gateway payload limits.
      # Keep this generous for large magazine PDFs and print artwork.
      MAGAZINE_MAX_UPLOAD_BYTES      = tostring(1024 * 1024 * 1024)
      MAGAZINE_ALLOWED_MIME_PREFIXES = "image/,application/pdf,application/zip,application/json,text/,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/rtf,application/vnd.oasis.opendocument.text,message/rfc822"
      MAGAZINE_ALLOWED_GROUPS        = join(",", ["committee", "admins", "webmaster"])
    }
  }

  tags = {
    Component = "magazine-production"
  }
}

resource "aws_lambda_permission" "magazine_api_gateway" {
  statement_id  = "AllowExecutionFromAPIGatewayMagazine"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.magazine_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.member_api.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "magazine_api" {
  api_id                 = aws_apigatewayv2_api.member_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.magazine_api.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

locals {
  magazine_api_routes = toset([
    "GET /member/magazine/bootstrap",
    "GET /member/magazine/issues",
    "POST /member/magazine/issues",
    "GET /member/magazine/content",
    "POST /member/magazine/content",
    "POST /member/magazine/content/extract",
    "POST /member/magazine/content/archive",
    "POST /member/magazine/flatplan/place",
    "POST /member/magazine/flatplan/page",
    "GET /member/magazine/templates",
    "POST /member/magazine/templates",
    "GET /member/magazine/assets",
    "GET /member/magazine/assets/file-data",
    "POST /member/magazine/assets/cleanup-duplicates",
    "POST /member/magazine/assets/delete",
    "POST /member/magazine/assets/upload-url",
    "POST /member/magazine/assets/confirm-upload",
    "GET /member/magazine/inbound",
    "POST /member/magazine/inbound/convert"
  ])
}

resource "aws_apigatewayv2_route" "magazine_api" {
  for_each = local.magazine_api_routes

  api_id             = aws_apigatewayv2_api.member_api.id
  route_key          = each.key
  target             = "integrations/${aws_apigatewayv2_integration.magazine_api.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}
