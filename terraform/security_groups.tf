resource "aws_security_group" "alb" {
  name        = "mlscan-alb-sg"
  description = "Allow caller EC2s to reach the ML scan ALB"
  vpc_id      = data.aws_vpc.main.id

  ingress {
    description     = "HTTP from caller EC2"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [var.caller_sg_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs_task" {
  name        = "mlscan-task-sg"
  description = "Allow traffic only from the ALB security group"
  vpc_id      = data.aws_vpc.main.id

  ingress {
    description     = "HTTP from ALB"
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
