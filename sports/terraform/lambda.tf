data "aws_caller_identity" "current" {}

resource "aws_iam_role" "lambda_role" {
  name = "${local.name_prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_dynamodb" {
  name = "${local.name_prefix}-lambda-dynamodb"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:BatchWriteItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem",
          "dynamodb:Scan",
          "dynamodb:Query",
          "dynamodb:DeleteItem"
        ]
        Resource = [
          aws_dynamodb_table.tournaments.arn,
          aws_dynamodb_table.players.arn,
          aws_dynamodb_table.events.arn,
          aws_dynamodb_table.sport_bodies.arn,
          aws_dynamodb_table.top_players.arn,
          aws_dynamodb_table.suggestions.arn,
          aws_dynamodb_table.activity_log.arn,
          aws_dynamodb_table.public_push_subscriptions.arn,
          aws_dynamodb_table.admin_devices.arn,
          aws_dynamodb_table.admin_prelogin_attempts.arn
        ]
      }
    ]
  })
}

data "archive_file" "api_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/api"
  output_path = "${path.module}/api.zip"
}

data "archive_file" "ingest_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/ingest"
  output_path = "${path.module}/ingest.zip"
}

resource "aws_lambda_function" "api" {
  function_name    = "${local.name_prefix}-api"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = var.lambda_runtime
  filename         = data.archive_file.api_zip.output_path
  source_code_hash = data.archive_file.api_zip.output_base64sha256
  timeout          = 12
  memory_size      = 256

  environment {
    variables = {
      TOURNAMENTS_TABLE               = aws_dynamodb_table.tournaments.name
      PLAYERS_TABLE                   = aws_dynamodb_table.players.name
      EVENTS_TABLE                    = aws_dynamodb_table.events.name
      SPORT_BODIES_TABLE              = aws_dynamodb_table.sport_bodies.name
      TOP_PLAYERS_TABLE               = aws_dynamodb_table.top_players.name
      SUGGESTIONS_TABLE               = aws_dynamodb_table.suggestions.name
      ACTIVITY_LOG_TABLE              = aws_dynamodb_table.activity_log.name
      PUBLIC_PUSH_SUBSCRIPTIONS_TABLE = aws_dynamodb_table.public_push_subscriptions.name
      ADMIN_DEVICES_TABLE             = aws_dynamodb_table.admin_devices.name
      ADMIN_PRELOGIN_ATTEMPTS_TABLE   = aws_dynamodb_table.admin_prelogin_attempts.name
      ADMIN_ALLOWED_GROUPS            = join(",", var.admin_allowed_groups)
      PRIMARY_ADMIN_GROUP             = "PrimaryAdmins"
      DEVICE_APPROVAL_TTL_SECONDS     = "1800"
      ADMIN_USER_POOL_ID              = aws_cognito_user_pool.admin.id
      ADMIN_APP_CLIENT_ID             = aws_cognito_user_pool_client.admin.id
      CORS_ALLOW_ORIGIN               = var.cors_allow_origin
    }
  }

  tags = local.common_tags
}

resource "aws_lambda_function" "ingest" {
  function_name    = "${local.name_prefix}-ingest"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = var.lambda_runtime
  filename         = data.archive_file.ingest_zip.output_path
  source_code_hash = data.archive_file.ingest_zip.output_base64sha256
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      TOURNAMENTS_TABLE  = aws_dynamodb_table.tournaments.name
      PLAYERS_TABLE      = aws_dynamodb_table.players.name
      EVENTS_TABLE       = aws_dynamodb_table.events.name
      SPORT_BODIES_TABLE = aws_dynamodb_table.sport_bodies.name
      TOP_PLAYERS_TABLE  = aws_dynamodb_table.top_players.name
    }
  }

  tags = local.common_tags
}


resource "aws_iam_role_policy" "lambda_cognito_admin_lookup" {
  name = "${local.name_prefix}-lambda-cognito-admin-lookup"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cognito-idp:ListUsers",
          "cognito-idp:AdminListGroupsForUser"
        ]
        Resource = aws_cognito_user_pool.admin.arn
      }
    ]
  })
}
