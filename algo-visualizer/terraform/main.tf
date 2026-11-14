locals {
  name = "algo-visualizer-${var.environment}"
}

# ---------------- Container registry ----------------
resource "aws_ecr_repository" "app" {
  name                 = "algo-visualizer"
  image_tag_mutability = "MUTABLE"
  force_delete         = var.environment != "prod"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 20 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 20
      }
      action = { type = "expire" }
    }]
  })
}

# ---------------- IAM: allow App Runner to pull from ECR ----------------
data "aws_iam_policy_document" "apprunner_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["build.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apprunner_ecr" {
  name               = "${local.name}-ecr-access"
  assume_role_policy = data.aws_iam_policy_document.apprunner_assume.json
}

resource "aws_iam_role_policy_attachment" "apprunner_ecr" {
  role       = aws_iam_role.apprunner_ecr.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

# ---------------- Autoscaling ----------------
resource "aws_apprunner_auto_scaling_configuration_version" "app" {
  auto_scaling_configuration_name = substr(local.name, 0, 32)
  min_size                        = var.min_instances
  max_size                        = var.max_instances
  max_concurrency                 = var.max_concurrency
}

# ---------------- Serverless container service ----------------
resource "aws_apprunner_service" "app" {
  service_name                   = local.name
  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.app.arn

  source_configuration {
    auto_deployments_enabled = false # CI decides when to deploy

    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_ecr.arn
    }

    image_repository {
      image_identifier      = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
      image_repository_type = "ECR"

      image_configuration {
        port = "8080"
        runtime_environment_variables = {
          APP_VERSION      = var.image_tag
          CLOUD_REGION     = var.region
          RATE_LIMIT_RPS   = "20"
          RATE_LIMIT_BURST = "60"
        }
      }
    }
  }

  instance_configuration {
    cpu    = var.cpu
    memory = var.memory
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/healthz"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 3
  }

  depends_on = [aws_iam_role_policy_attachment.apprunner_ecr]
}

# ---------------- Observability: alarm on 5xx ----------------
resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${local.name}-5xx"
  namespace           = "AWS/AppRunner"
  metric_name         = "5xxStatusResponses"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    ServiceName = aws_apprunner_service.app.service_name
    ServiceID   = aws_apprunner_service.app.service_id
  }
}
