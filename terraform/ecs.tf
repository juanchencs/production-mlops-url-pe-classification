resource "aws_cloudwatch_log_group" "url" {
  name = "/ecs/mlscan-url"
}

resource "aws_cloudwatch_log_group" "pe" {
  name = "/ecs/mlscan-pe"
}

resource "aws_ecs_cluster" "main" {
  name = "mlscan-cluster"
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

# ---------------------------------------------------------------------------
# URL service task definition
# container_definitions is ignored after creation so CI can update the image
# tag without Terraform reverting it on the next apply.
# ---------------------------------------------------------------------------
resource "aws_ecs_task_definition" "url" {
  family                   = "url-task"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  task_role_arn            = aws_iam_role.ecs_task.arn
  execution_role_arn       = data.aws_iam_role.ecs_execution.arn

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([{
    name  = "app"
    image = "${aws_ecr_repository.models.repository_url}:url-init"
    portMappings = [{
      containerPort = 8080
      protocol      = "tcp"
      appProtocol   = "http"
    }]
    environment = [
      { name = "AWS_REGION",          value = var.aws_region },
      { name = "THRESHOLD",           value = "30" },
      { name = "MODEL_MODE",          value = "real" },
      { name = "API_KEY_SECRET_NAME", value = aws_secretsmanager_secret.api_key.name }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.url.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])

  lifecycle {
    ignore_changes = [container_definitions]
  }
}

# ---------------------------------------------------------------------------
# PE service task definition
# ---------------------------------------------------------------------------
resource "aws_ecs_task_definition" "pe" {
  family                   = "pe-task"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  task_role_arn            = aws_iam_role.ecs_task.arn
  execution_role_arn       = data.aws_iam_role.ecs_execution.arn

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([{
    name  = "app"
    image = "${aws_ecr_repository.models.repository_url}:pe-init"
    portMappings = [{
      containerPort = 8080
      protocol      = "tcp"
      appProtocol   = "http"
    }]
    environment = [
      { name = "AWS_REGION",          value = var.aws_region },
      { name = "THRESHOLD",           value = "30" },
      { name = "MODEL_MODE",          value = "real" },
      { name = "API_KEY_SECRET_NAME", value = aws_secretsmanager_secret.api_key.name }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.pe.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])

  lifecycle {
    ignore_changes = [container_definitions]
  }
}

# ---------------------------------------------------------------------------
# ECS services
# task_definition is ignored after creation — CI updates it via RegisterTaskDefinition
# ---------------------------------------------------------------------------
resource "aws_ecs_service" "url" {
  name            = "url-svc"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.url.arn
  desired_count   = 1

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }

  network_configuration {
    subnets          = var.ecs_subnet_ids
    security_groups  = [aws_security_group.ecs_task.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.url.arn
    container_name   = "app"
    container_port   = 8080
  }

  health_check_grace_period_seconds  = 120
  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener_rule.url]
}

resource "aws_ecs_service" "pe" {
  name            = "pe-svc"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.pe.arn
  desired_count   = 1

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }

  network_configuration {
    subnets          = var.ecs_subnet_ids
    security_groups  = [aws_security_group.ecs_task.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.pe.arn
    container_name   = "app"
    container_port   = 8080
  }

  health_check_grace_period_seconds  = 120
  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener_rule.pe]
}
