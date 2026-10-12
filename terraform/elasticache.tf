resource "random_password" "redis_token" {
  length  = 32
  special = true
}

resource "aws_elasticache_parameter_group" "main" {
  family = "redis7"
  name   = "${var.app_name}-redis-params"

  tags = {
    Name = "${var.app_name}-redis-params"
  }
}

resource "aws_elasticache_cluster" "main" {
  cluster_id           = "${var.app_name}-redis"
  engine               = "redis"
  engine_version       = var.cache_engine_version
  node_type            = var.cache_node_type
  num_cache_nodes      = 1
  parameter_group_name = aws_elasticache_parameter_group.main.name
  port                 = 6379

  subnet_group_name           = aws_elasticache_subnet_group.main.name
  security_group_ids          = [aws_security_group.redis_sg.id]
  az_mode                     = "single-az"
  maintenance_window          = "mon:05:00-mon:06:00"
  auto_minor_version_upgrade  = true
  apply_immediately           = false

  tags = {
    Name = "${var.app_name}-redis"
  }
}
