output "ecr_repository_url" {
  description = "docker push target"
  value       = aws_ecr_repository.app.repository_url
}

output "service_url" {
  description = "Public HTTPS URL of the app"
  value       = "https://${aws_apprunner_service.app.service_url}"
}

output "service_arn" {
  value = aws_apprunner_service.app.arn
}
